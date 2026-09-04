import glob,json,os,sys
from collections import defaultdict
from datetime import datetime,timedelta

sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3

TRAIN=("2021-01-01","2022-12-31")
VAL1=("2023-01-01","2023-12-31")
VAL2=("2024-01-01","2024-12-31")
FINAL=("2025-01-01","2026-02-28")
INITIAL=100000.0
FRICTION=0.005
TARGET=0.12
STOP=0.045
HORIZON=7
SLOTS=2
WEEKLY_TARGET=0.02

BREADTH_THRESHOLDS=[0.35,0.375,0.40,0.425,0.45,0.50]
CONFIRM_MODES=[
    "next_close_above_resistance",
    "next_close_above_breakout_close",
    "two_closes_above_resistance",
    "retest_reclaim_within_2",
]
MIN_WEALTH_RATIO=0.98
MIN_DD_REDUCTION=0.10
MIN_ACTIVE_GE2_RATIO=0.95
MIN_TRADES=12


def in_period(d,p): return p[0] <= d <= p[1]

def week_start(s):
    d=datetime.fromisoformat(s).date()
    return (d-timedelta(days=(d.weekday()+1)%7)).isoformat()

def mean(a): return sum(a)/len(a) if a else 0.0

def maxdd(curve):
    peak=-1.0; peak_date=None; mdd=0.0; dd_peak=dd_trough=None
    for r in curve:
        e=r["equity"]
        if e>peak:
            peak=e; peak_date=r["date"]
        dd=e/peak-1 if peak>0 else 0.0
        if dd<mdd:
            mdd=dd; dd_peak=peak_date; dd_trough=r["date"]
    return mdd,dd_peak,dd_trough

def weekly(curve):
    by=defaultdict(list)
    for r in curve: by[week_start(r["date"])].append(r)
    prev=INITIAL; vals=[]; active=[]; hit_any=0
    for wk in sorted(by):
        arr=by[wk]; end=arr[-1]["equity"]
        ret=end/prev-1 if prev>0 else 0.0
        vals.append(ret)
        is_active=any(x["exposure"]>1e-9 for x in arr)
        if is_active: active.append(ret)
        mx=max(x["equity"] for x in arr)/prev-1 if prev>0 else 0.0
        hit_any += mx>=WEEKLY_TARGET
        prev=end
    return {
        "weeks":len(vals),"avg":mean(vals),
        "positive_rate":sum(x>0 for x in vals)/len(vals) if vals else 0,
        "weekend_ge_2_rate":sum(x>=WEEKLY_TARGET for x in vals)/len(vals) if vals else 0,
        "hit_2_anytime_rate":hit_any/len(vals) if vals else 0,
        "active_weeks":len(active),"active_avg":mean(active),
        "active_positive_rate":sum(x>0 for x in active)/len(active) if active else 0,
        "active_ge_2_rate":sum(x>=WEEKLY_TARGET for x in active)/len(active) if active else 0,
        "worst":min(vals) if vals else 0,"best":max(vals) if vals else 0,
    }

def collect(sym,rows,market):
    out=[]; nxt=60; t=60
    while t < len(rows)-HORIZON-2:
        if t<nxt:
            t+=1; continue
        ms=[]
        for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
            c=v3.v1_candidate(rows,t,n)
            if c: ms.append(c)
        if ms:
            c=max(ms,key=lambda x:x["base_n"])
            s=v3.make_signal(sym,rows,t,c,market)
            if s and s["v2_flag"]>0:
                out.append({
                    "symbol":sym,"breakout_index":t,"breakout_date":rows[t]["date"],
                    "breakout_close":rows[t]["close"],"resistance":c["base_high"],
                    "liquidity":c["median_base_value"],"breadth20":s["market_breadth20"],
                    "market5":s["market5_ret"],"market20":s["market20_ret"],"rs20":s["rs20"],
                    "breakout_vol_ratio":s["breakout_vol_ratio"],"clv":s["clv"],"body":s["body"],
                    "nearest_overhead":s["nearest_overhead_pct"],
                })
            nxt=t+11
        t+=1
    return out

def trade_outcome(rows,entry_i):
    e=rows[entry_i]["close"]; tgt=e*(1+TARGET); stp=e*(1-STOP)
    fut=rows[entry_i+1:entry_i+1+HORIZON]
    if len(fut)<HORIZON:return None
    for h,d in enumerate(fut,1):
        if d["low"]<=stp:
            return {"entry":e,"entry_date":rows[entry_i]["date"],"exit_date":d["date"],"exit_price":stp,"gross_return":-STOP,"exit_type":"stop","holding":h}
        if d["high"]>=tgt:
            return {"entry":e,"entry_date":rows[entry_i]["date"],"exit_date":d["date"],"exit_price":tgt,"gross_return":TARGET,"exit_type":"target","holding":h}
    d=fut[-1]
    return {"entry":e,"entry_date":rows[entry_i]["date"],"exit_date":d["date"],"exit_price":d["close"],"gross_return":d["close"]/e-1,"exit_type":"timeout","holding":HORIZON}

def confirm_index(rows,sig,mode):
    t=sig["breakout_index"]; r=sig["resistance"]; bc=sig["breakout_close"]
    if t+2>=len(rows): return None
    d1=rows[t+1]; d2=rows[t+2]
    if mode=="next_close_above_resistance":
        return t+1 if d1["close"]>r else None
    if mode=="next_close_above_breakout_close":
        return t+1 if d1["close"]>=bc else None
    if mode=="two_closes_above_resistance":
        return t+2 if d1["close"]>r and d2["close"]>r else None
    if mode=="retest_reclaim_within_2":
        for j in (t+1,t+2):
            d=rows[j]
            if d["low"]<=r*1.01 and d["close"]>r:
                return j
        return None
    raise ValueError(mode)

def build_trades(signals,data,breadth_threshold=None,confirm_mode=None):
    out=[]; diag={"low_breadth_signals":0,"confirm_pass":0,"confirm_fail":0,"delayed_1":0,"delayed_2":0}
    for s in signals:
        rows=data[s["symbol"]]; bi=s["breakout_index"]
        use_confirm=(breadth_threshold is not None and s["breadth20"]<=breadth_threshold)
        ei=bi
        if use_confirm:
            diag["low_breadth_signals"]+=1
            ei=confirm_index(rows,s,confirm_mode)
            if ei is None:
                diag["confirm_fail"]+=1; continue
            diag["confirm_pass"]+=1
            diag["delayed_1" if ei-bi==1 else "delayed_2"]+=1
        o=trade_outcome(rows,ei)
        if o is None: continue
        out.append({**o,"symbol":s["symbol"],"liquidity":s["liquidity"],"original_breakout_date":s["breakout_date"],"breadth20_at_breakout":s["breadth20"],"confirmed":use_confirm,"delay_sessions":ei-bi})
    return out,diag

def build_maps(data):
    closes={}; dates=set()
    for s,rows in data.items():
        closes[s]={r["date"]:r["close"] for r in rows}; dates.update(closes[s])
    return closes,sorted(dates)

def simulate(trades,data,period):
    closes,all_dates=build_maps(data); dates=[d for d in all_dates if period[0]<=d<=period[1]]
    eb=defaultdict(list); xb=defaultdict(list)
    for t in trades:
        if in_period(t["entry_date"],period) and t["exit_date"]<=period[1]:
            eb[t["entry_date"]].append(t); xb[t["exit_date"]].append(t)
    for d in eb: eb[d].sort(key=lambda x:(-x["liquidity"],x["symbol"]))
    half=FRICTION/2; cash=INITIAL; pos={}; last={}; curve=[]; real=[]; skip=defaultdict(int)
    def mark(d):
        pv=0.0
        for s,q in pos.items():
            px=closes.get(s,{}).get(d)
            if px is not None:last[s]=px
            pv+=q["shares"]*last.get(s,q["entry"])
        return cash+pv,pv
    for d in dates:
        for s in list(pos):
            px=closes.get(s,{}).get(d)
            if px is not None:last[s]=px
        for tr in sorted(xb.get(d,[]),key=lambda x:x["symbol"]):
            s=tr["symbol"]
            if s not in pos:continue
            q=pos.pop(s); proceeds=q["shares"]*tr["exit_price"]*(1-half); cash+=proceeds
            real.append({"symbol":s,"entry_date":q["entry_date"],"exit_date":d,"net_return":proceeds/q["budget"]-1,"exit_type":tr["exit_type"],"holding":tr["holding"],"confirmed":tr["confirmed"],"breadth20_at_breakout":tr["breadth20_at_breakout"]})
        for tr in eb.get(d,[]):
            if tr["symbol"] in pos:
                skip["duplicate_symbol"]+=1; continue
            if len(pos)>=SLOTS:
                skip["max_positions"]+=1; continue
            eq,_=mark(d); budget=min(eq*0.50,cash)
            if budget<=1:
                skip["cash"]+=1; continue
            invested=budget*(1-half); shares=invested/tr["entry"]; cash-=budget
            pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"entry_date":d,"budget":budget}; last[tr["symbol"]]=tr["entry"]
        eq,pv=mark(d); curve.append({"date":d,"equity":eq,"exposure":pv/eq if eq else 0,"open":len(pos)})
    mdd,pd,td=maxdd(curve); final=curve[-1]["equity"]
    d0=datetime.fromisoformat(curve[0]["date"]).date(); d1=datetime.fromisoformat(curve[-1]["date"]).date(); yrs=max((d1-d0).days/365.25,1/365.25)
    rs=[x["net_return"] for x in real]
    return {"trades":len(real),"skipped":sum(skip.values()),"skip_reasons":dict(skip),"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,"max_drawdown":mdd,"dd_peak":pd,"dd_trough":td,"avg_trade_return":mean(rs),"positive_trade_rate":sum(x>0 for x in rs)/len(rs) if rs else 0,"confirmed_trades":sum(x["confirmed"] for x in real),"weekly":weekly(curve),"avg_exposure":mean([x["exposure"] for x in curve]),"curve":curve,"realized":real}

def slim(x): return {k:v for k,v in x.items() if k not in {"curve","realized"}}

def breadth_bins(signals,data,period):
    bins=[("<35%",0,0.35),("35-40%",0.35,0.40),("40-45%",0.40,0.45),("45-50%",0.45,0.50),(">=50%",0.50,2.0)]
    out=[]
    for name,lo,hi in bins:
        arr=[]
        for s in signals:
            if not in_period(s["breakout_date"],period): continue
            b=s["breadth20"]
            if not (lo<=b<hi): continue
            o=trade_outcome(data[s["symbol"]],s["breakout_index"])
            if o: arr.append(o)
        out.append({"bin":name,"signals":len(arr),"targets":sum(x["exit_type"]=="target" for x in arr),"stops":sum(x["exit_type"]=="stop" for x in arr),"timeouts":sum(x["exit_type"]=="timeout" for x in arr),"target_rate":sum(x["exit_type"]=="target" for x in arr)/len(arr) if arr else None,"stop_rate":sum(x["exit_type"]=="stop" for x in arr)/len(arr) if arr else None,"avg_gross_return":mean([x["gross_return"] for x in arr]) if arr else None})
    return out

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw")
    files=sorted(glob.glob(os.path.join(root,"*","*.csv"))); data={}
    for fp in files:
        s=os.path.basename(fp).split(".")[0].upper(); rows=v3.load_csv_all(fp)
        if len(rows)>=100:data[s]=rows
    market=v3.build_market_maps(data); signals=[]
    for s,rows in data.items(): signals+=collect(s,rows,market)

    baseline_trades,_=build_trades(signals,data,None,None)
    b23=simulate(baseline_trades,data,VAL1); b24=simulate(baseline_trades,data,VAL2); bf=simulate(baseline_trades,data,FINAL)
    diagnostics={"train_2021_2022":breadth_bins(signals,data,TRAIN),"2023":breadth_bins(signals,data,VAL1),"2024":breadth_bins(signals,data,VAL2),"final_research_period":breadth_bins(signals,data,FINAL)}

    eligible=[]; allrows=[]; tested=0
    for bt in BREADTH_THRESHOLDS:
        for mode in CONFIRM_MODES:
            tested+=1
            tr,diag=build_trades(signals,data,bt,mode)
            a=simulate(tr,data,VAL1); b=simulate(tr,data,VAL2)
            if a["trades"]<MIN_TRADES or b["trades"]<MIN_TRADES: continue
            wr1=(1+a["total_return"])/(1+b23["total_return"]); wr2=(1+b["total_return"])/(1+b24["total_return"])
            dr1=1-abs(a["max_drawdown"])/abs(b23["max_drawdown"]); dr2=1-abs(b["max_drawdown"])/abs(b24["max_drawdown"])
            ar1=a["weekly"]["active_ge_2_rate"]/b23["weekly"]["active_ge_2_rate"] if b23["weekly"]["active_ge_2_rate"] else 1
            ar2=b["weekly"]["active_ge_2_rate"]/b24["weekly"]["active_ge_2_rate"] if b24["weekly"]["active_ge_2_rate"] else 1
            row={"config":{"breadth_threshold":bt,"confirm_mode":mode},"confirmation_diagnostics_all_periods":diag,"2023":slim(a),"2024":slim(b),"min_wealth_ratio":min(wr1,wr2),"min_dd_reduction":min(dr1,dr2),"min_active_ge2_ratio":min(ar1,ar2),"min_cagr":min(a["cagr"],b["cagr"])}
            allrows.append(row)
            if row["min_wealth_ratio"]>=MIN_WEALTH_RATIO and row["min_dd_reduction"]>=MIN_DD_REDUCTION and row["min_active_ge2_ratio"]>=MIN_ACTIVE_GE2_RATIO:
                eligible.append(row)
    eligible.sort(key=lambda z:(z["min_wealth_ratio"],z["min_dd_reduction"],z["min_active_ge2_ratio"],z["min_cagr"]),reverse=True)
    allrows.sort(key=lambda z:(z["min_wealth_ratio"],z["min_dd_reduction"],z["min_active_ge2_ratio"]),reverse=True)
    best=eligible[0] if eligible else None
    final_result=None; final_cmp=None
    if best:
        tr,_=build_trades(signals,data,best["config"]["breadth_threshold"],best["config"]["confirm_mode"])
        fin=simulate(tr,data,FINAL); final_result=slim(fin)
        final_cmp={"wealth_ratio":(1+fin["total_return"])/(1+bf["total_return"]),"drawdown_reduction":1-abs(fin["max_drawdown"])/abs(bf["max_drawdown"]),"return_change_pp":100*(fin["total_return"]-bf["total_return"]),"dd_change_pp":100*(abs(bf["max_drawdown"])-abs(fin["max_drawdown"])),"active_week_avg_change_pp":100*(fin["weekly"]["active_avg"]-bf["weekly"]["active_avg"]),"active_ge2_rate_ratio":fin["weekly"]["active_ge_2_rate"]/bf["weekly"]["active_ge_2_rate"] if bf["weekly"]["active_ge_2_rate"] else None}

    result={
        "pattern":"Defensive Lift v5.5 Breadth-Conditional Confirmation",
        "goal":"test whether low market breadth predicts DLP failure and require observable post-breakout confirmation only in low-breadth conditions, without resizing positions",
        "fixed":{"base_entry":"frozen v2 DLP","target":TARGET,"stop":STOP,"holding_after_actual_entry":HORIZON,"slots":SLOTS,"slot_size":0.50,"friction_round_trip":FRICTION,"ranking":"v3.2 liquidity"},
        "protocol":{"diagnostic_train":TRAIN,"validation_2023":VAL1,"validation_2024":VAL2,"final_research_period":FINAL,"final_not_used_for_selection":True,"min_wealth_ratio_each_validation":MIN_WEALTH_RATIO,"min_dd_reduction_each_validation":MIN_DD_REDUCTION,"min_active_ge2_ratio_each_validation":MIN_ACTIVE_GE2_RATIO},
        "dataset":{"stocks":len(data),"signals":len(signals)},
        "breadth_diagnostics":diagnostics,
        "baseline_v32":{"2023":slim(b23),"2024":slim(b24),"final":slim(bf)},
        "grid":{"breadth_thresholds":BREADTH_THRESHOLDS,"confirmation_modes":CONFIRM_MODES,"tested":tested,"eligible":len(eligible)},
        "selected":best,"final_result":final_result,"comparison_final":final_cmp,"top20":eligible[:20],"best_near_misses":allrows[:20],
    }
    with open("tmp/egx_backtest/results_v55_breadth_confirmation.json","w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result.get(k) for k in ["pattern","protocol","dataset","breadth_diagnostics","baseline_v32","grid","selected","final_result","comparison_final","best_near_misses"]},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
