import glob, json, math, os, sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3

VAL1=("2023-01-01","2023-12-31")
VAL2=("2024-01-01","2024-12-31")
FINAL=("2025-01-01","2026-02-28")
INITIAL=100000.0
FRICTION=0.005
TARGET=0.12
INITIAL_STOP=0.045
HORIZON=7
SLOTS=2
WEEKLY_TARGET=0.02

# Risk compression after the trade proves itself. No reduction of the +12% target.
PROTECT_TRIGGERS=[0.02,0.03,0.04,0.05]
PROTECT_STOPS=[-0.02,-0.01,0.0,0.01]
LOCK_TRIGGERS=[0.06,0.08,0.10]
LOCK_STOPS=[0.02,0.03,0.04,0.05]
WEEKLY_LOSS_LOCKS=[None,0.015,0.02,0.025,0.03]

# Strict research constraints: protect or improve return while materially reducing DD in validation.
MIN_RETURN_RATIO=0.98
MIN_DD_REDUCTION=0.10
MIN_TRADES=15


def in_period(d,p):return p[0]<=d<=p[1]

def week_start(s):
    d=datetime.fromisoformat(s).date();delta=(d.weekday()+1)%7
    return (d-timedelta(days=delta)).isoformat()

def collect_v2(sym,rows,market):
    out=[];next_allowed=v3.MAX_BASE;t=max(v3.MAX_BASE,60)
    while t<len(rows)-HORIZON:
        if t<next_allowed:t+=1;continue
        ms=[]
        for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
            c=v3.v1_candidate(rows,t,n)
            if c:ms.append(c)
        if ms:
            c=max(ms,key=lambda x:x["base_n"]);s=v3.make_signal(sym,rows,t,c,market)
            if s and s["v2_flag"]>0:
                out.append({"symbol":sym,"entry_date":rows[t]["date"],"entry":rows[t]["close"],"median_base_value":c["median_base_value"],"future":rows[t+1:t+1+HORIZON]})
            next_allowed=t+v3.COOLDOWN+1
        t+=1
    return out

def finalize_static(tr):
    e=tr["entry"];tgt=e*(1+TARGET);stp=e*(1-INITIAL_STOP);f=tr["future"][:HORIZON]
    for i,d in enumerate(f,1):
        if d["low"]<=stp:return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":stp,"gross_return":-INITIAL_STOP,"exit_type":"stop","holding_sessions":i}
        if d["high"]>=tgt:return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":tgt,"gross_return":TARGET,"exit_type":"target","holding_sessions":i}
    d=f[-1];return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":d["close"],"gross_return":d["close"]/e-1,"exit_type":"timeout","holding_sessions":HORIZON}

def finalize_dynamic(tr,cfg):
    e=tr["entry"];tgt=e*(1+TARGET);active_stop=e*(1-INITIAL_STOP);f=tr["future"][:HORIZON]
    stage=0
    for i,d in enumerate(f,1):
        # Existing stop and target ambiguity is handled conservatively: stop first.
        if d["low"]<=active_stop:
            r=active_stop/e-1
            return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":active_stop,"gross_return":r,"exit_type":"dynamic_stop","holding_sessions":i,"stop_stage":stage}
        if d["high"]>=tgt:
            return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":tgt,"gross_return":TARGET,"exit_type":"target","holding_sessions":i,"stop_stage":stage}
        # Intraday trigger ambiguity: if trigger and newly raised stop are both inside same daily bar,
        # assume trigger occurred first and then the new stop was hit. This is conservative versus holding.
        new_stop=active_stop;new_stage=stage
        if d["high"]>=e*(1+cfg["lock_trigger"]):
            new_stop=max(new_stop,e*(1+cfg["lock_stop"]));new_stage=2
        elif d["high"]>=e*(1+cfg["protect_trigger"]):
            new_stop=max(new_stop,e*(1+cfg["protect_stop"]));new_stage=max(new_stage,1)
        if new_stop>active_stop:
            if d["low"]<=new_stop:
                r=new_stop/e-1
                return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":new_stop,"gross_return":r,"exit_type":"same_day_raised_stop","holding_sessions":i,"stop_stage":new_stage}
            active_stop=new_stop;stage=new_stage
    d=f[-1];return {**{k:tr[k] for k in ["symbol","entry_date","entry","median_base_value"]},"exit_date":d["date"],"exit_price":d["close"],"gross_return":d["close"]/e-1,"exit_type":"timeout","holding_sessions":HORIZON,"stop_stage":stage}

def maxdd(curve):
    peak=-1;m=0;pd=td=None;rp=None
    for r in curve:
        e=r["equity"]
        if e>peak:peak=e;rp=r["date"]
        dd=e/peak-1 if peak>0 else 0
        if dd<m:m=dd;pd=rp;td=r["date"]
    return m,pd,td

def weekly_metrics(curve):
    by=defaultdict(list)
    for r in curve:by[week_start(r["date"])].append(r)
    prev=INITIAL;arr=[]
    for wk in sorted(by):
        rs=by[wk];end=rs[-1]["equity"];ret=end/prev-1 if prev>0 else 0;mx=max(x["equity"] for x in rs)/prev-1 if prev>0 else 0
        arr.append({"week":wk,"return":ret,"hit_2pct_anytime":mx>=WEEKLY_TARGET});prev=end
    vals=[x["return"] for x in arr]
    return {"weeks":len(arr),"avg":sum(vals)/len(vals) if vals else None,"median":v3.median(vals) if vals else None,"positive_rate":sum(1 for x in vals if x>0)/len(vals) if vals else None,"weekend_ge_2_rate":sum(1 for x in vals if x>=WEEKLY_TARGET)/len(vals) if vals else None,"hit_2_anytime_rate":sum(1 for x in arr if x["hit_2pct_anytime"])/len(arr) if arr else None,"worst":min(vals) if vals else None,"best":max(vals) if vals else None}

def build_maps(data):
    closes={};dates=set()
    for sym,rows in data.items():closes[sym]={r["date"]:r["close"] for r in rows};dates.update(closes[sym])
    return closes,sorted(dates)

def simulate(trades,closes,all_dates,period,weekly_loss_lock=None):
    eb=defaultdict(list);xb=defaultdict(list)
    for t in trades:eb[t["entry_date"]].append(t);xb[t["exit_date"]].append(t)
    for d in eb:eb[d].sort(key=lambda x:(-x["median_base_value"],x["symbol"]))
    dates=[d for d in all_dates if period[0]<=d<=period[1]];half=FRICTION/2;cash=INITIAL;pos={};last={};curve=[];real=[];skipped=0
    wk=None;wk_start_eq=INITIAL;locked=False
    def mark(d):
        pv=0
        for sym,p in pos.items():
            px=closes.get(sym,{}).get(d)
            if px is not None:last[sym]=px
            pv+=p["shares"]*last.get(sym,p["entry"])
        return cash+pv,pv
    for d in dates:
        w=week_start(d)
        if w!=wk:
            eq0,_=mark(d);wk=w;wk_start_eq=eq0;locked=False
        for sym in list(pos):
            px=closes.get(sym,{}).get(d)
            if px is not None:last[sym]=px
        for tr in sorted(xb.get(d,[]),key=lambda x:x["symbol"]):
            sym=tr["symbol"]
            if sym not in pos:continue
            p=pos.pop(sym);proceeds=p["shares"]*tr["exit_price"]*(1-half);cash+=proceeds;real.append(proceeds/p["budget"]-1)
        eq,_=mark(d)
        if weekly_loss_lock is not None and eq/wk_start_eq-1<=-weekly_loss_lock:locked=True
        for tr in eb.get(d,[]):
            if locked or len(pos)>=SLOTS:skipped+=1;continue
            eq,_=mark(d);budget=min(eq/SLOTS,cash)
            if budget<=1:skipped+=1;continue
            invested=budget*(1-half);shares=invested/tr["entry"];cash-=budget;pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"budget":budget};last[tr["symbol"]]=tr["entry"]
        eq,pv=mark(d);curve.append({"date":d,"equity":eq,"open":len(pos),"exposure":pv/eq if eq>0 else 0})
    mdd,pd,td=maxdd(curve);final=curve[-1]["equity"];d0=datetime.fromisoformat(curve[0]["date"]).date();d1=datetime.fromisoformat(curve[-1]["date"]).date();yrs=max((d1-d0).days/365.25,1/365.25);wm=weekly_metrics(curve)
    return {"trades":len(real),"skipped":skipped,"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,"max_drawdown":mdd,"dd_peak":pd,"dd_trough":td,"avg_trade_return":sum(real)/len(real) if real else None,"positive_trade_rate":sum(1 for x in real if x>0)/len(real) if real else None,"weekly":wm}

def eval_period(raw,closes,dates,p,cfg=None,baseline=False):
    ts=[]
    for x in raw:
        if not in_period(x["entry_date"],p):continue
        t=finalize_static(x) if baseline else finalize_dynamic(x,cfg)
        if t["exit_date"]<=p[1]:ts.append(t)
    return simulate(ts,closes,dates,p,None if baseline else cfg["weekly_loss_lock"])

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw");files=sorted(glob.glob(os.path.join(root,"*","*.csv")));data={}
    for p in files:
        sym=os.path.basename(p).split(".")[0].upper();rows=v3.load_csv_all(p)
        if len(rows)>=100:data[sym]=rows
    market=v3.build_market_maps(data);raw=[]
    for sym,rows in data.items():raw.extend(collect_v2(sym,rows,market))
    closes,dates=build_maps(data)
    b23=eval_period(raw,closes,dates,VAL1,baseline=True);b24=eval_period(raw,closes,dates,VAL2,baseline=True);bf=eval_period(raw,closes,dates,FINAL,baseline=True)
    ranked=[];tested=0
    for pt in PROTECT_TRIGGERS:
     for ps in PROTECT_STOPS:
      if ps>=pt:continue
      for lt in LOCK_TRIGGERS:
       if lt<=pt:continue
       for ls in LOCK_STOPS:
        if ls>=lt or ls<ps:continue
        for wll in WEEKLY_LOSS_LOCKS:
         tested+=1;cfg={"protect_trigger":pt,"protect_stop":ps,"lock_trigger":lt,"lock_stop":ls,"weekly_loss_lock":wll}
         a=eval_period(raw,closes,dates,VAL1,cfg);b=eval_period(raw,closes,dates,VAL2,cfg)
         if a["trades"]<MIN_TRADES or b["trades"]<MIN_TRADES:continue
         rr1=(1+a["total_return"])/(1+b23["total_return"])-1;rr2=(1+b["total_return"])/(1+b24["total_return"])-1
         # Preserve at least 98% of baseline ending wealth in BOTH validation years.
         wealth_ratio1=(1+a["total_return"])/(1+b23["total_return"]);wealth_ratio2=(1+b["total_return"])/(1+b24["total_return"])
         ddred1=1-abs(a["max_drawdown"])/abs(b23["max_drawdown"]) if b23["max_drawdown"] else 0
         ddred2=1-abs(b["max_drawdown"])/abs(b24["max_drawdown"]) if b24["max_drawdown"] else 0
         if min(wealth_ratio1,wealth_ratio2)<MIN_RETURN_RATIO:continue
         if min(ddred1,ddred2)<MIN_DD_REDUCTION:continue
         min_cagr=min(a["cagr"],b["cagr"]);min_week2=min(a["weekly"]["weekend_ge_2_rate"],b["weekly"]["weekend_ge_2_rate"])
         ranked.append({"config":cfg,"2023":a,"2024":b,"min_wealth_ratio_vs_v32":min(wealth_ratio1,wealth_ratio2),"min_dd_reduction":min(ddred1,ddred2),"min_cagr":min_cagr,"min_weekend_2_rate":min_week2})
    ranked.sort(key=lambda x:(x["min_cagr"],x["min_dd_reduction"],x["min_wealth_ratio_vs_v32"],x["min_weekend_2_rate"]),reverse=True)
    result={"pattern":"Defensive Lift v3.5 Profit Preservation Risk Engine","goal":"keep +12% upside and v3.2 capital concentration while compressing losses after price proves itself","fixed":{"target":TARGET,"initial_stop":INITIAL_STOP,"horizon":HORIZON,"slots":SLOTS,"friction_round_trip":FRICTION},"protocol":{"validation_2023":VAL1,"validation_2024":VAL2,"final_holdout":FINAL,"final_not_used_for_selection":True,"min_validation_ending_wealth_ratio_vs_v32":MIN_RETURN_RATIO,"min_validation_drawdown_reduction_vs_v32":MIN_DD_REDUCTION},"grid":{"tested":tested,"eligible":len(ranked),"protect_triggers":PROTECT_TRIGGERS,"protect_stops":PROTECT_STOPS,"lock_triggers":LOCK_TRIGGERS,"lock_stops":LOCK_STOPS,"weekly_loss_locks":WEEKLY_LOSS_LOCKS},"baseline_v32":{"2023":b23,"2024":b24,"final":bf}}
    if ranked:
        best=ranked[0];fin=eval_period(raw,closes,dates,FINAL,best["config"]);result["selected"]={**best};result["final_result"]=fin;result["comparison_final"]={"v32_total_return":bf["total_return"],"v35_total_return":fin["total_return"],"v32_max_drawdown":bf["max_drawdown"],"v35_max_drawdown":fin["max_drawdown"],"return_change_relative":(1+fin["total_return"])/(1+bf["total_return"])-1,"drawdown_reduction":1-abs(fin["max_drawdown"])/abs(bf["max_drawdown"]),"v32_weekend_2_rate":bf["weekly"]["weekend_ge_2_rate"],"v35_weekend_2_rate":fin["weekly"]["weekend_ge_2_rate"],"v32_positive_week_rate":bf["weekly"]["positive_rate"],"v35_positive_week_rate":fin["weekly"]["positive_rate"]};result["top20"]=ranked[:20]
    else:
        result["selected"]=None;result["final_result"]=None;result["conclusion"]="No configuration preserved >=98% of v3.2 ending wealth AND reduced drawdown >=10% in both validation years."
    with open("tmp/egx_backtest/results_v35_profit_preservation.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result.get(k) for k in ["pattern","protocol","grid","baseline_v32","selected","final_result","comparison_final","conclusion"]},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
