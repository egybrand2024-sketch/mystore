import glob, json, math, os, sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, "tmp/egx_backtest")
import backtest_v3_ml as v3

CAL1=("2023-01-01","2023-12-31")
CAL2=("2024-01-01","2024-12-31")
FINAL=("2025-01-01","2026-02-28")
INITIAL_CAPITAL=100000.0
FRICTION=0.005
MAX_H=15

TARGETS=[0.08,0.10,0.12]
STOPS=[0.035,0.04,0.045,0.05]
HORIZONS=[5,7,10,12,15]
SLOTS=[2,3,4,5]
MAX_DD_ALLOWED=0.12
MIN_TRADES_PER_VALIDATION=12

BASELINE={"target":0.12,"stop":0.045,"horizon":15,"slots":5}


def in_period(d,p): return p[0] <= d <= p[1]

def collect_v2(sym,rows,market):
    out=[]; next_allowed=v3.MAX_BASE; t=max(v3.MAX_BASE,60)
    while t < len(rows)-MAX_H:
        if t<next_allowed: t+=1; continue
        matches=[]
        for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
            c=v3.v1_candidate(rows,t,n)
            if c: matches.append(c)
        if matches:
            c=max(matches,key=lambda x:x["base_n"])
            s=v3.make_signal(sym,rows,t,c,market)
            if s and s["v2_flag"]>0:
                out.append({"symbol":sym,"entry_date":rows[t]["date"],"entry":rows[t]["close"],"median_base_value":c["median_base_value"],"future":rows[t+1:t+1+MAX_H]})
            next_allowed=t+v3.COOLDOWN+1
        t+=1
    return out

def finalize(tr,target,stop,horizon):
    entry=tr["entry"]; tgt=entry*(1+target); stp=entry*(1-stop); fut=tr["future"][:horizon]
    for i,d in enumerate(fut,1):
        if d["low"]<=stp:
            return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":stp,"gross_return":-stop,"exit_type":"stop","holding_sessions":i}
        if d["high"]>=tgt:
            return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":tgt,"gross_return":target,"exit_type":"target","holding_sessions":i}
    d=fut[-1]
    return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":d["close"],"gross_return":d["close"]/entry-1,"exit_type":"timeout","holding_sessions":horizon}

def max_dd(curve):
    peak=-1; mdd=0; pdate=tdate=None; rp=None
    for r in curve:
        e=r["equity"]
        if e>peak: peak=e; rp=r["date"]
        dd=e/peak-1 if peak>0 else 0
        if dd<mdd: mdd=dd; pdate=rp; tdate=r["date"]
    return mdd,pdate,tdate

def first_hit(curve,ret):
    target=INITIAL_CAPITAL*(1+ret)
    for r in curve:
        if r["equity"]>=target: return r["date"]
    return None

def months_between(a,b):
    if not a or not b: return None
    d0=datetime.fromisoformat(a).date(); d1=datetime.fromisoformat(b).date()
    return (d1-d0).days/30.4375

def simulate(trades,data,slots,period):
    if not trades:
        return None
    eb=defaultdict(list); xb=defaultdict(list)
    for t in trades: eb[t["entry_date"]].append(t); xb[t["exit_date"]].append(t)
    for d in eb: eb[d].sort(key=lambda x:(-x["median_base_value"],x["symbol"]))
    close={}; dates=set()
    for sym,rows in data.items():
        m={r["date"]:r["close"] for r in rows}; close[sym]=m; dates.update(m)
    dates=[d for d in sorted(dates) if period[0]<=d<=period[1]]
    half=FRICTION/2; cash=INITIAL_CAPITAL; pos={}; last={}; curve=[]; realized=[]; skipped=0
    def equity(d):
        pv=0
        for sym,p in pos.items():
            px=close.get(sym,{}).get(d)
            if px is not None: last[sym]=px
            pv += p["shares"]*last.get(sym,p["entry"])
        return cash+pv,pv
    for d in dates:
        for sym in list(pos):
            px=close.get(sym,{}).get(d)
            if px is not None: last[sym]=px
        for tr in sorted(xb.get(d,[]),key=lambda x:x["symbol"]):
            sym=tr["symbol"]
            if sym not in pos: continue
            p=pos.pop(sym); proceeds=p["shares"]*tr["exit_price"]*(1-half); cash+=proceeds
            realized.append({"symbol":sym,"entry_date":p["entry_date"],"exit_date":d,"net_return":proceeds/p["budget"]-1,"exit_type":tr["exit_type"],"holding_sessions":tr["holding_sessions"]})
        for tr in eb.get(d,[]):
            if len(pos)>=slots: skipped+=1; continue
            eq,_=equity(d); budget=min(eq/slots,cash)
            if budget<=1: skipped+=1; continue
            invested=budget*(1-half); shares=invested/tr["entry"]; cash-=budget
            pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"entry_date":d,"budget":budget}; last[tr["symbol"]]=tr["entry"]
        eq,pv=equity(d); curve.append({"date":d,"equity":eq,"open":len(pos),"exposure":pv/eq if eq>0 else 0})
    # force no open positions expected because trade exits are within period if entry near period end may extend beyond; exclude those trades before simulate.
    if not curve: return None
    mdd,pd,td=max_dd(curve); final_eq=curve[-1]["equity"]
    start=curve[0]["date"]; end=curve[-1]["date"]
    yrs=max((datetime.fromisoformat(end).date()-datetime.fromisoformat(start).date()).days/365.25,1/365.25)
    cagr=(final_eq/INITIAL_CAPITAL)**(1/yrs)-1 if final_eq>0 else -1
    rets=[x["net_return"] for x in realized]
    holds=[x["holding_sessions"] for x in realized]
    return {"slots":slots,"trades":len(realized),"skipped":skipped,"final_equity":final_eq,"total_return":final_eq/INITIAL_CAPITAL-1,"cagr":cagr,"max_drawdown":mdd,"dd_peak":pd,"dd_trough":td,"avg_trade_return":sum(rets)/len(rets) if rets else None,"positive_rate":sum(1 for x in rets if x>0)/len(rets) if rets else None,"avg_holding_sessions":sum(holds)/len(holds) if holds else None,"median_holding_sessions":v3.median(holds) if holds else None,"hit_25_date":first_hit(curve,0.25),"hit_40_date":first_hit(curve,0.40),"hit_50_date":first_hit(curve,0.50),"months_to_25":months_between(start,first_hit(curve,0.25)),"months_to_40":months_between(start,first_hit(curve,0.40)),"months_to_50":months_between(start,first_hit(curve,0.50)),"curve":curve,"realized":realized}

def period_eval(raw,data,period,cfg):
    trs=[]
    for x in raw:
        if not in_period(x["entry_date"],period): continue
        f=finalize(x,cfg["target"],cfg["stop"],cfg["horizon"])
        if f["exit_date"]<=period[1]: trs.append(f)
    return simulate(trs,data,cfg["slots"],period)

def slim(x): return {k:v for k,v in x.items() if k not in {"curve","realized"}}

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw"); files=sorted(glob.glob(os.path.join(root,"*","*.csv")))
    data={}
    for p in files:
        sym=os.path.basename(p).split(".")[0].upper(); rows=v3.load_csv_all(p)
        if len(rows)>=100:data[sym]=rows
    market=v3.build_market_maps(data); raw=[]
    for sym,rows in data.items(): raw.extend(collect_v2(sym,rows,market))

    candidates=[]
    for target in TARGETS:
      for stop in STOPS:
       for horizon in HORIZONS:
        for slots in SLOTS:
            cfg={"target":target,"stop":stop,"horizon":horizon,"slots":slots}
            a=period_eval(raw,data,CAL1,cfg); b=period_eval(raw,data,CAL2,cfg)
            if not a or not b or a["trades"]<MIN_TRADES_PER_VALIDATION or b["trades"]<MIN_TRADES_PER_VALIDATION: continue
            if abs(a["max_drawdown"])>MAX_DD_ALLOWED or abs(b["max_drawdown"])>MAX_DD_ALLOWED: continue
            # time-efficiency score: prefer the weaker validation CAGR, then lower holding time, then lower DD.
            score=min(a["cagr"],b["cagr"])
            candidates.append({"cfg":cfg,"2023":slim(a),"2024":slim(b),"score":score,"avg_hold":(a["avg_holding_sessions"]+b["avg_holding_sessions"])/2,"worst_dd":max(abs(a["max_drawdown"]),abs(b["max_drawdown"]))})
    candidates.sort(key=lambda x:(x["score"],-x["avg_hold"],-x["worst_dd"]),reverse=True)
    best=candidates[0]
    final=period_eval(raw,data,FINAL,best["cfg"])
    base23=period_eval(raw,data,CAL1,BASELINE); base24=period_eval(raw,data,CAL2,BASELINE); basef=period_eval(raw,data,FINAL,BASELINE)

    result={"pattern":"Defensive Lift v3.2 time-efficiency research","goal":"reduce time-to-return / improve capital velocity without selecting on 2025-2026","friction_round_trip_assumption":FRICTION,"selection_protocol":{"validation_1":CAL1,"validation_2":CAL2,"final_holdout":FINAL,"final_not_used_for_selection":True,"max_validation_drawdown":MAX_DD_ALLOWED,"ranking":"maximize weaker validation-year CAGR; tie-break shorter average holding then lower drawdown"},"grid":{"targets":TARGETS,"stops":STOPS,"horizons":HORIZONS,"slots":SLOTS,"eligible":len(candidates)},"baseline_v31":{"config":BASELINE,"2023":slim(base23),"2024":slim(base24),"final":slim(basef)},"selected":{"config":best["cfg"],"2023":best["2023"],"2024":best["2024"],"score":best["score"],"avg_hold_validation":best["avg_hold"],"worst_dd_validation":best["worst_dd"]},"final_result":slim(final),"comparison_final":{"baseline_total_return":basef["total_return"],"candidate_total_return":final["total_return"],"baseline_cagr":basef["cagr"],"candidate_cagr":final["cagr"],"baseline_max_drawdown":basef["max_drawdown"],"candidate_max_drawdown":final["max_drawdown"],"baseline_avg_holding":basef["avg_holding_sessions"],"candidate_avg_holding":final["avg_holding_sessions"],"baseline_months_to_25":basef["months_to_25"],"candidate_months_to_25":final["months_to_25"],"baseline_months_to_40":basef["months_to_40"],"candidate_months_to_40":final["months_to_40"],"baseline_months_to_50":basef["months_to_50"],"candidate_months_to_50":final["months_to_50"]},"top20":candidates[:20]}
    with open("tmp/egx_backtest/results_v32_time_efficiency.json","w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ["pattern","selection_protocol","grid","baseline_v31","selected","final_result","comparison_final"]},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
