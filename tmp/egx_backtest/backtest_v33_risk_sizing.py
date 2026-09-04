import glob, json, os, sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3

VAL1=("2023-01-01","2023-12-31")
VAL2=("2024-01-01","2024-12-31")
FINAL=("2025-01-01","2026-02-28")
TARGET=0.12
STOP=0.045
HORIZON=7
INITIAL=100000.0
FRICTION=0.005
RISK_PER_TRADE=[0.005,0.0075,0.01]
MAX_OPEN_RISK=[0.01,0.015,0.02,0.025,0.03]
MAX_POSITIONS=[2,3,4,5]
MAX_VALIDATION_DD=0.10
MIN_TRADES=12


def in_period(d,p): return p[0] <= d <= p[1]

def collect_v2(sym,rows,market):
    out=[]; next_allowed=v3.MAX_BASE; t=max(v3.MAX_BASE,60)
    while t < len(rows)-HORIZON:
        if t<next_allowed: t+=1; continue
        matches=[]
        for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
            c=v3.v1_candidate(rows,t,n)
            if c: matches.append(c)
        if matches:
            c=max(matches,key=lambda x:x["base_n"])
            s=v3.make_signal(sym,rows,t,c,market)
            if s and s["v2_flag"]>0:
                out.append({"symbol":sym,"entry_date":rows[t]["date"],"entry":rows[t]["close"],"median_base_value":c["median_base_value"],"future":rows[t+1:t+1+HORIZON]})
            next_allowed=t+v3.COOLDOWN+1
        t+=1
    return out

def finalize(tr):
    entry=tr["entry"]; tgt=entry*(1+TARGET); stp=entry*(1-STOP); fut=tr["future"][:HORIZON]
    for i,d in enumerate(fut,1):
        if d["low"]<=stp:
            return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":stp,"gross_return":-STOP,"exit_type":"stop","holding_sessions":i}
        if d["high"]>=tgt:
            return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":tgt,"gross_return":TARGET,"exit_type":"target","holding_sessions":i}
    d=fut[-1]
    return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":d["close"],"gross_return":d["close"]/entry-1,"exit_type":"timeout","holding_sessions":HORIZON}

def maxdd(curve):
    peak=-1; m=0; pd=td=None; rp=None
    for r in curve:
        e=r["equity"]
        if e>peak: peak=e; rp=r["date"]
        dd=e/peak-1 if peak>0 else 0
        if dd<m: m=dd; pd=rp; td=r["date"]
    return m,pd,td

def longest_loss(rs):
    b=c=0
    for r in rs:
        if r<0: c+=1; b=max(b,c)
        else: c=0
    return b

def simulate(trades,data,period,risk_per_trade,max_open_risk,max_positions):
    eb=defaultdict(list); xb=defaultdict(list)
    for t in trades: eb[t["entry_date"]].append(t); xb[t["exit_date"]].append(t)
    for d in eb: eb[d].sort(key=lambda x:(-x["median_base_value"],x["symbol"]))
    closes={}; dates=set()
    for sym,rows in data.items():
        m={r["date"]:r["close"] for r in rows}; closes[sym]=m; dates.update(m)
    dates=[d for d in sorted(dates) if period[0]<=d<=period[1]]
    half=FRICTION/2; cash=INITIAL; pos={}; last={}; curve=[]; realized=[]; skipped=[]
    def mark(d):
        pv=0
        for sym,p in pos.items():
            px=closes.get(sym,{}).get(d)
            if px is not None: last[sym]=px
            pv += p["shares"]*last.get(sym,p["entry"])
        return cash+pv,pv
    for d in dates:
        for sym in list(pos):
            px=closes.get(sym,{}).get(d)
            if px is not None: last[sym]=px
        for tr in sorted(xb.get(d,[]),key=lambda x:x["symbol"]):
            sym=tr["symbol"]
            if sym not in pos: continue
            p=pos.pop(sym); proceeds=p["shares"]*tr["exit_price"]*(1-half); cash+=proceeds
            realized.append({"symbol":sym,"entry_date":p["entry_date"],"exit_date":d,"net_return":proceeds/p["budget"]-1,"portfolio_risk_at_entry":p["risk_frac"],"exit_type":tr["exit_type"],"holding_sessions":tr["holding_sessions"]})
        for tr in eb.get(d,[]):
            eq,_=mark(d)
            open_risk=sum(p["risk_amount"] for p in pos.values())/eq if eq>0 else 1
            if len(pos)>=max_positions:
                skipped.append({"symbol":tr["symbol"],"date":d,"reason":"max_positions"}); continue
            if open_risk + risk_per_trade > max_open_risk + 1e-12:
                skipped.append({"symbol":tr["symbol"],"date":d,"reason":"max_open_risk"}); continue
            risk_amount=eq*risk_per_trade
            desired_value=risk_amount/STOP
            budget=min(desired_value,cash)
            if budget<=1:
                skipped.append({"symbol":tr["symbol"],"date":d,"reason":"cash"}); continue
            actual_risk=budget*STOP
            invested=budget*(1-half); shares=invested/tr["entry"]; cash-=budget
            pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"entry_date":d,"budget":budget,"risk_amount":actual_risk,"risk_frac":actual_risk/eq if eq>0 else 0}
            last[tr["symbol"]]=tr["entry"]
        eq,pv=mark(d); open_risk_amt=sum(p["risk_amount"] for p in pos.values()); curve.append({"date":d,"equity":eq,"open_positions":len(pos),"exposure":pv/eq if eq>0 else 0,"planned_open_risk":open_risk_amt/eq if eq>0 else 0})
    if not curve: return None
    mdd,pd,td=maxdd(curve); final=curve[-1]["equity"]
    d0=datetime.fromisoformat(curve[0]["date"]).date(); d1=datetime.fromisoformat(curve[-1]["date"]).date(); yrs=max((d1-d0).days/365.25,1/365.25)
    cagr=(final/INITIAL)**(1/yrs)-1 if final>0 else -1
    rs=[x["net_return"] for x in realized]; holds=[x["holding_sessions"] for x in realized]
    return {"risk_per_trade":risk_per_trade,"max_open_risk":max_open_risk,"max_positions":max_positions,"trades":len(realized),"skipped":len(skipped),"final_equity":final,"total_return":final/INITIAL-1,"cagr":cagr,"max_drawdown":mdd,"dd_peak":pd,"dd_trough":td,"avg_net_trade_return":sum(rs)/len(rs) if rs else None,"positive_rate":sum(1 for r in rs if r>0)/len(rs) if rs else None,"longest_losing_streak":longest_loss(rs),"avg_holding":sum(holds)/len(holds) if holds else None,"median_holding":v3.median(holds) if holds else None,"avg_exposure":sum(x["exposure"] for x in curve)/len(curve),"max_exposure":max(x["exposure"] for x in curve),"avg_planned_open_risk":sum(x["planned_open_risk"] for x in curve)/len(curve),"max_planned_open_risk":max(x["planned_open_risk"] for x in curve)}

def eval_period(raw,data,p,cfg):
    ts=[]
    for x in raw:
        if not in_period(x["entry_date"],p): continue
        t=finalize(x)
        if t["exit_date"]<=p[1]: ts.append(t)
    return simulate(ts,data,p,**cfg)

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw"); files=sorted(glob.glob(os.path.join(root,"*","*.csv")))
    data={}
    for p in files:
        sym=os.path.basename(p).split(".")[0].upper(); rows=v3.load_csv_all(p)
        if len(rows)>=100:data[sym]=rows
    market=v3.build_market_maps(data); raw=[]
    for sym,rows in data.items(): raw.extend(collect_v2(sym,rows,market))
    ranked=[]
    for rpt in RISK_PER_TRADE:
      for mor in MAX_OPEN_RISK:
       if mor+1e-12<rpt: continue
       for mp in MAX_POSITIONS:
        cfg={"risk_per_trade":rpt,"max_open_risk":mor,"max_positions":mp}
        a=eval_period(raw,data,VAL1,cfg); b=eval_period(raw,data,VAL2,cfg)
        if not a or not b or a["trades"]<MIN_TRADES or b["trades"]<MIN_TRADES: continue
        if abs(a["max_drawdown"])>MAX_VALIDATION_DD or abs(b["max_drawdown"])>MAX_VALIDATION_DD: continue
        score=min(a["cagr"],b["cagr"])
        ranked.append({"config":cfg,"2023":a,"2024":b,"score":score,"worst_dd":max(abs(a["max_drawdown"]),abs(b["max_drawdown"]))})
    ranked.sort(key=lambda x:(x["score"],-x["worst_dd"],x["2023"]["trades"]+x["2024"]["trades"]),reverse=True)
    best=ranked[0]; final=eval_period(raw,data,FINAL,best["config"])
    # explicit conservative reference: 0.75% risk/trade, 1.5% total open risk, up to 3 positions
    refcfg={"risk_per_trade":0.0075,"max_open_risk":0.015,"max_positions":3}
    ref23=eval_period(raw,data,VAL1,refcfg); ref24=eval_period(raw,data,VAL2,refcfg); reff=eval_period(raw,data,FINAL,refcfg)
    result={"pattern":"Defensive Lift v3.3 risk-based sizing research","fixed_trade_management":{"target":TARGET,"stop":STOP,"horizon":HORIZON},"friction_round_trip":FRICTION,"protocol":{"validation_1":VAL1,"validation_2":VAL2,"final_holdout":FINAL,"final_not_used_for_selection":True,"max_validation_drawdown":MAX_VALIDATION_DD,"ranking":"maximize weaker validation-year CAGR, then lower worst drawdown"},"grid":{"risk_per_trade":RISK_PER_TRADE,"max_open_risk":MAX_OPEN_RISK,"max_positions":MAX_POSITIONS,"eligible":len(ranked)},"selected":{"config":best["config"],"2023":best["2023"],"2024":best["2024"],"score":best["score"],"worst_dd":best["worst_dd"]},"final_result":final,"conservative_reference":{"config":refcfg,"2023":ref23,"2024":ref24,"final":reff},"top20":ranked[:20]}
    with open("tmp/egx_backtest/results_v33_risk_sizing.json","w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ["pattern","fixed_trade_management","protocol","grid","selected","final_result","conservative_reference"]},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
