import glob, json, math, os, sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, "tmp/egx_backtest")
import backtest_v3_ml as v3

VAL1=("2023-01-01","2023-12-31")
VAL2=("2024-01-01","2024-12-31")
FINAL=("2025-01-01","2026-02-28")
TARGET=0.12
STOP=0.045
HORIZON=7
INITIAL=100000.0
FRICTION=0.005

# Expanded weekly risk-budget search.
RISK_PER_TRADE=[0.006,0.007,0.008,0.009,0.010]
MAX_OPEN_RISK=[0.016,0.020,0.024,0.028,0.032]
MAX_POSITIONS=[2,3,4,5]
WEEKLY_LOSS_LIMIT=[0.012,0.016,0.020,0.024]
GAIN_RISK_MULT=[0.0,0.5,1.0]
LOSS_RISK_MULT=[0.5,0.75,1.0]
WEEKLY_TARGET=0.02
MAX_VALIDATION_DD=0.08
MIN_VALIDATION_CAGR=0.25
MIN_TRADES=15

# Mathematical anchor: with a 4.5% stop, 0.8% portfolio risk implies a 17.78% position.
# A +12% target then contributes ~2.13% gross portfolio return, or ~2.04% after 0.5% round-trip friction.
ANCHOR={"risk_per_trade":0.008,"max_open_risk":0.024,"max_positions":3,"weekly_loss_limit":0.016,"gain_risk_mult":0.5,"loss_risk_mult":0.5}


def in_period(d,p): return p[0] <= d <= p[1]

def week_start(date_str):
    d=datetime.fromisoformat(date_str).date()
    # EGX trading week is Sunday-Thursday. Python weekday: Mon=0,...Sun=6.
    delta=(d.weekday()+1)%7
    return (d-timedelta(days=delta)).isoformat()

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
        if r<0:c+=1;b=max(b,c)
        else:c=0
    return b

def weekly_metrics(curve):
    if not curve:return {}
    by=defaultdict(list)
    for r in curve: by[week_start(r["date"])].append(r)
    weeks=[]
    prev_end=INITIAL
    for wk in sorted(by):
        arr=by[wk]; start_eq=prev_end; end_eq=arr[-1]["equity"]
        ret=end_eq/start_eq-1 if start_eq>0 else 0
        max_eq=max(x["equity"] for x in arr); min_eq=min(x["equity"] for x in arr)
        intramax=max_eq/start_eq-1 if start_eq>0 else 0
        intramin=min_eq/start_eq-1 if start_eq>0 else 0
        weeks.append({"week":wk,"start_equity":start_eq,"end_equity":end_eq,"return":ret,"intrawEEK_max":intramax,"intrawEEK_min":intramin,"hit_2pct_anytime":intramax>=WEEKLY_TARGET})
        prev_end=end_eq
    rs=[w["return"] for w in weeks]
    return {
        "weeks":len(weeks),
        "avg_weekly_return":sum(rs)/len(rs) if rs else None,
        "median_weekly_return":v3.median(rs) if rs else None,
        "positive_week_rate":sum(1 for r in rs if r>0)/len(rs) if rs else None,
        "weeks_ge_2pct":sum(1 for r in rs if r>=WEEKLY_TARGET),
        "weekend_2pct_rate":sum(1 for r in rs if r>=WEEKLY_TARGET)/len(rs) if rs else None,
        "weeks_hit_2pct_anytime":sum(1 for w in weeks if w["hit_2pct_anytime"]),
        "intrawEEK_2pct_hit_rate":sum(1 for w in weeks if w["hit_2pct_anytime"])/len(weeks) if weeks else None,
        "losing_week_rate":sum(1 for r in rs if r<0)/len(rs) if rs else None,
        "worst_week":min(rs) if rs else None,
        "best_week":max(rs) if rs else None,
        "weekly_std":math.sqrt(sum((r-sum(rs)/len(rs))**2 for r in rs)/len(rs)) if rs else None,
        "detail":weeks,
    }

def build_market_data(data):
    closes={}; dates=set()
    for sym,rows in data.items():
        closes[sym]={r["date"]:r["close"] for r in rows}; dates.update(closes[sym])
    return closes,sorted(dates)

def simulate_dynamic(trades,data,period,cfg):
    eb=defaultdict(list); xb=defaultdict(list)
    for t in trades: eb[t["entry_date"]].append(t); xb[t["exit_date"]].append(t)
    for d in eb: eb[d].sort(key=lambda x:(-x["median_base_value"],x["symbol"]))
    closes,all_dates=build_market_data(data); dates=[d for d in all_dates if period[0]<=d<=period[1]]
    half=FRICTION/2; cash=INITIAL; pos={}; last={}; curve=[]; realized=[]; skipped=[]
    current_week=None; week_start_equity=INITIAL; week_locked_loss=False
    def mark(d):
        pv=0
        for sym,p in pos.items():
            px=closes.get(sym,{}).get(d)
            if px is not None:last[sym]=px
            pv+=p["shares"]*last.get(sym,p["entry"])
        return cash+pv,pv
    for d in dates:
        wk=week_start(d)
        if wk!=current_week:
            eq0,_=mark(d)
            current_week=wk; week_start_equity=eq0; week_locked_loss=False
        for sym in list(pos):
            px=closes.get(sym,{}).get(d)
            if px is not None:last[sym]=px
        for tr in sorted(xb.get(d,[]),key=lambda x:x["symbol"]):
            sym=tr["symbol"]
            if sym not in pos:continue
            p=pos.pop(sym); proceeds=p["shares"]*tr["exit_price"]*(1-half); cash+=proceeds
            realized.append({"symbol":sym,"entry_date":p["entry_date"],"exit_date":d,"net_return":proceeds/p["budget"]-1,"portfolio_risk_at_entry":p["risk_frac"],"exit_type":tr["exit_type"],"holding_sessions":tr["holding_sessions"]})
        for tr in eb.get(d,[]):
            eq,_=mark(d); week_ret=eq/week_start_equity-1 if week_start_equity>0 else 0
            if week_ret<=-cfg["weekly_loss_limit"]: week_locked_loss=True
            if week_locked_loss:
                skipped.append({"symbol":tr["symbol"],"date":d,"reason":"weekly_loss_lock"});continue
            risk_mult=1.0
            if week_ret>=WEEKLY_TARGET:risk_mult*=cfg["gain_risk_mult"]
            elif week_ret<=-cfg["weekly_loss_limit"]/2:risk_mult*=cfg["loss_risk_mult"]
            eff_risk=cfg["risk_per_trade"]*risk_mult
            if eff_risk<=0:
                skipped.append({"symbol":tr["symbol"],"date":d,"reason":"weekly_gain_lock"});continue
            open_risk=sum(p["risk_amount"] for p in pos.values())/eq if eq>0 else 1
            if len(pos)>=cfg["max_positions"]:
                skipped.append({"symbol":tr["symbol"],"date":d,"reason":"max_positions"});continue
            if open_risk+eff_risk>cfg["max_open_risk"]+1e-12:
                skipped.append({"symbol":tr["symbol"],"date":d,"reason":"max_open_risk"});continue
            risk_amount=eq*eff_risk; desired_value=risk_amount/STOP; budget=min(desired_value,cash)
            if budget<=1:
                skipped.append({"symbol":tr["symbol"],"date":d,"reason":"cash"});continue
            actual_risk=budget*STOP; invested=budget*(1-half); shares=invested/tr["entry"]; cash-=budget
            pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"entry_date":d,"budget":budget,"risk_amount":actual_risk,"risk_frac":actual_risk/eq if eq>0 else 0}
            last[tr["symbol"]]=tr["entry"]
        eq,pv=mark(d); wr=eq/week_start_equity-1 if week_start_equity>0 else 0
        curve.append({"date":d,"equity":eq,"open_positions":len(pos),"exposure":pv/eq if eq>0 else 0,"week_return_mark":wr,"planned_open_risk":sum(p["risk_amount"] for p in pos.values())/eq if eq>0 else 0})
    if not curve:return None
    mdd,pd,td=maxdd(curve); final=curve[-1]["equity"]
    d0=datetime.fromisoformat(curve[0]["date"]).date();d1=datetime.fromisoformat(curve[-1]["date"]).date();yrs=max((d1-d0).days/365.25,1/365.25)
    cagr=(final/INITIAL)**(1/yrs)-1 if final>0 else -1
    rs=[x["net_return"] for x in realized];holds=[x["holding_sessions"] for x in realized];wm=weekly_metrics(curve)
    return {"config":cfg,"trades":len(realized),"skipped":len(skipped),"final_equity":final,"total_return":final/INITIAL-1,"cagr":cagr,"max_drawdown":mdd,"dd_peak":pd,"dd_trough":td,"avg_net_trade_return":sum(rs)/len(rs) if rs else None,"positive_trade_rate":sum(1 for r in rs if r>0)/len(rs) if rs else None,"longest_losing_streak":longest_loss(rs),"avg_holding":sum(holds)/len(holds) if holds else None,"avg_exposure":sum(x["exposure"] for x in curve)/len(curve),"max_exposure":max(x["exposure"] for x in curve),"max_planned_open_risk":max(x["planned_open_risk"] for x in curve),"weekly":{k:v for k,v in wm.items() if k!="detail"},"curve":curve,"weekly_detail":wm.get("detail",[]),"skipped_detail":skipped}

def simulate_v32_baseline(trades,data,period):
    # Frozen v3.2 comparison: 2 equal equity slots, +12/-4.5/7, 0.5% friction.
    eb=defaultdict(list);xb=defaultdict(list)
    for t in trades:eb[t["entry_date"]].append(t);xb[t["exit_date"]].append(t)
    for d in eb:eb[d].sort(key=lambda x:(-x["median_base_value"],x["symbol"]))
    closes,all_dates=build_market_data(data);dates=[d for d in all_dates if period[0]<=d<=period[1]]
    half=FRICTION/2;cash=INITIAL;pos={};last={};curve=[];realized=[];skipped=0
    def mark(d):
        pv=0
        for sym,p in pos.items():
            px=closes.get(sym,{}).get(d)
            if px is not None:last[sym]=px
            pv+=p["shares"]*last.get(sym,p["entry"])
        return cash+pv,pv
    for d in dates:
        for sym in list(pos):
            px=closes.get(sym,{}).get(d)
            if px is not None:last[sym]=px
        for tr in sorted(xb.get(d,[]),key=lambda x:x["symbol"]):
            if tr["symbol"] not in pos:continue
            p=pos.pop(tr["symbol"]);proceeds=p["shares"]*tr["exit_price"]*(1-half);cash+=proceeds;realized.append(proceeds/p["budget"]-1)
        for tr in eb.get(d,[]):
            if len(pos)>=2:skipped+=1;continue
            eq,_=mark(d);budget=min(eq/2,cash)
            if budget<=1:skipped+=1;continue
            invested=budget*(1-half);shares=invested/tr["entry"];cash-=budget;pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"budget":budget};last[tr["symbol"]]=tr["entry"]
        eq,pv=mark(d);curve.append({"date":d,"equity":eq,"open_positions":len(pos),"exposure":pv/eq if eq>0 else 0})
    mdd,pd,td=maxdd(curve);final=curve[-1]["equity"];d0=datetime.fromisoformat(curve[0]["date"]).date();d1=datetime.fromisoformat(curve[-1]["date"]).date();yrs=max((d1-d0).days/365.25,1/365.25);wm=weekly_metrics(curve)
    return {"trades":len(realized),"skipped":skipped,"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,"max_drawdown":mdd,"weekly":{k:v for k,v in wm.items() if k!="detail"}}

def eval_period(raw,data,p,cfg=None,baseline=False):
    ts=[]
    for x in raw:
        if not in_period(x["entry_date"],p):continue
        t=finalize(x)
        if t["exit_date"]<=p[1]:ts.append(t)
    return simulate_v32_baseline(ts,data,p) if baseline else simulate_dynamic(ts,data,p,cfg)

def slim(x):return {k:v for k,v in x.items() if k not in {"curve","weekly_detail","skipped_detail"}}

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw");files=sorted(glob.glob(os.path.join(root,"*","*.csv")))
    data={}
    for p in files:
        sym=os.path.basename(p).split(".")[0].upper();rows=v3.load_csv_all(p)
        if len(rows)>=100:data[sym]=rows
    market=v3.build_market_maps(data);raw=[]
    for sym,rows in data.items():raw.extend(collect_v2(sym,rows,market))
    base23=eval_period(raw,data,VAL1,baseline=True);base24=eval_period(raw,data,VAL2,baseline=True);basef=eval_period(raw,data,FINAL,baseline=True)
    ranked=[]
    for rpt in RISK_PER_TRADE:
      for mor in MAX_OPEN_RISK:
       if mor+1e-12<rpt:continue
       for mp in MAX_POSITIONS:
        if mor>rpt*mp+1e-12:continue
        for wll in WEEKLY_LOSS_LIMIT:
         for grm in GAIN_RISK_MULT:
          for lrm in LOSS_RISK_MULT:
            cfg={"risk_per_trade":rpt,"max_open_risk":mor,"max_positions":mp,"weekly_loss_limit":wll,"gain_risk_mult":grm,"loss_risk_mult":lrm}
            a=eval_period(raw,data,VAL1,cfg);b=eval_period(raw,data,VAL2,cfg)
            if not a or not b or a["trades"]<MIN_TRADES or b["trades"]<MIN_TRADES:continue
            if abs(a["max_drawdown"])>MAX_VALIDATION_DD or abs(b["max_drawdown"])>MAX_VALIDATION_DD:continue
            if min(a["cagr"],b["cagr"])<MIN_VALIDATION_CAGR:continue
            hit=min(a["weekly"]["weekend_2pct_rate"],b["weekly"]["weekend_2pct_rate"])
            avg_hit=(a["weekly"]["weekend_2pct_rate"]+b["weekly"]["weekend_2pct_rate"])/2
            min_cagr=min(a["cagr"],b["cagr"]);worstdd=max(abs(a["max_drawdown"]),abs(b["max_drawdown"]))
            ranked.append({"config":cfg,"2023":slim(a),"2024":slim(b),"min_weekend_2pct_rate":hit,"avg_weekend_2pct_rate":avg_hit,"min_cagr":min_cagr,"worst_dd":worstdd})
    ranked.sort(key=lambda x:(x["min_weekend_2pct_rate"],x["avg_weekend_2pct_rate"],x["min_cagr"],-x["worst_dd"]),reverse=True)
    if not ranked:raise RuntimeError("No v3.4 configs met validation constraints")
    best=ranked[0];final=eval_period(raw,data,FINAL,best["config"])
    a23=eval_period(raw,data,VAL1,ANCHOR);a24=eval_period(raw,data,VAL2,ANCHOR);af=eval_period(raw,data,FINAL,ANCHOR)
    result={"pattern":"Defensive Lift v3.4 Weekly Risk Budget Engine","goal":"target 2%+ portfolio weeks without forcing profit-taking; reduce downside via weekly risk throttles","fixed_trade_management":{"target":TARGET,"stop":STOP,"horizon":HORIZON},"friction_round_trip":FRICTION,"math_anchor":{"risk_per_trade":0.008,"implied_position_size":0.008/STOP,"gross_portfolio_gain_if_target_hit":(0.008/STOP)*TARGET,"approx_round_trip_cost_on_portfolio":(0.008/STOP)*FRICTION,"approx_net_portfolio_gain_if_target_hit":(0.008/STOP)*(TARGET-FRICTION)},"protocol":{"validation_1":VAL1,"validation_2":VAL2,"final_holdout":FINAL,"final_not_used_for_selection":True,"max_validation_drawdown":MAX_VALIDATION_DD,"min_validation_cagr":MIN_VALIDATION_CAGR,"ranking":"maximize weaker validation-year week-end >=2% hit rate, then average hit rate, then weaker CAGR, then lower drawdown"},"baseline_v32":{"2023":base23,"2024":base24,"final":basef},"grid":{"risk_per_trade":RISK_PER_TRADE,"max_open_risk":MAX_OPEN_RISK,"max_positions":MAX_POSITIONS,"weekly_loss_limit":WEEKLY_LOSS_LIMIT,"gain_risk_mult":GAIN_RISK_MULT,"loss_risk_mult":LOSS_RISK_MULT,"eligible":len(ranked)},"selected":{"config":best["config"],"2023":best["2023"],"2024":best["2024"],"min_weekend_2pct_rate":best["min_weekend_2pct_rate"],"avg_weekend_2pct_rate":best["avg_weekend_2pct_rate"],"min_cagr":best["min_cagr"],"worst_dd":best["worst_dd"]},"final_result":slim(final),"anchor_reference":{"config":ANCHOR,"2023":slim(a23),"2024":slim(a24),"final":slim(af)},"comparison_final":{"v32_total_return":basef["total_return"],"v34_total_return":final["total_return"],"v32_max_drawdown":basef["max_drawdown"],"v34_max_drawdown":final["max_drawdown"],"v32_weekend_2pct_rate":basef["weekly"]["weekend_2pct_rate"],"v34_weekend_2pct_rate":final["weekly"]["weekend_2pct_rate"],"v32_positive_week_rate":basef["weekly"]["positive_week_rate"],"v34_positive_week_rate":final["weekly"]["positive_week_rate"],"v32_worst_week":basef["weekly"]["worst_week"],"v34_worst_week":final["weekly"]["worst_week"]},"top20":ranked[:20]}
    with open("tmp/egx_backtest/results_v34_weekly_engine.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ["pattern","math_anchor","protocol","baseline_v32","grid","selected","final_result","anchor_reference","comparison_final"]},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
