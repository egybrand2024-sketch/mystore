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

# Small, interpretable grid only. The goal is to detect early failure without cutting right-tail winners.
CHECK_DAYS=[1,2,3]
CLOSE_THRESHOLDS=[-0.01,-0.02,-0.03]
MFE_THRESHOLDS=[0.00,0.01,0.02]
MODE=["close_only","close_and_low_mfe","below_breakout_close"]

MIN_WEALTH_RATIO=0.98
MIN_DD_REDUCTION=0.10
MIN_ACTIVE_GE2_RATIO=0.95
MIN_TRADES=12


def in_period(d,p): return p[0] <= d <= p[1]

def week_start(s):
    d=datetime.fromisoformat(s).date(); return (d-timedelta(days=(d.weekday()+1)%7)).isoformat()

def mean(a): return sum(a)/len(a) if a else 0.0

def maxdd(curve):
    peak=-1; peak_date=None; mdd=0; pd=td=None
    for r in curve:
        e=r["equity"]
        if e>peak:
            peak=e; peak_date=r["date"]
        dd=e/peak-1 if peak>0 else 0
        if dd<mdd:
            mdd=dd; pd=peak_date; td=r["date"]
    return mdd,pd,td

def weekly(curve):
    by=defaultdict(list)
    for r in curve: by[week_start(r["date"])].append(r)
    prev=INITIAL; vals=[]; active=[]; hit_any=0
    for wk in sorted(by):
        arr=by[wk]; end=arr[-1]["equity"]
        ret=end/prev-1 if prev>0 else 0
        vals.append(ret)
        if any(x["exposure"]>1e-9 for x in arr): active.append(ret)
        if prev>0 and max(x["equity"] for x in arr)/prev-1>=WEEKLY_TARGET: hit_any+=1
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
    while t < len(rows)-HORIZON:
        if t<nxt:
            t+=1; continue
        ms=[]
        for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
            c=v3.v1_candidate(rows,t,n)
            if c: ms.append(c)
        if ms:
            c=max(ms,key=lambda x:x["base_n"]); s=v3.make_signal(sym,rows,t,c,market)
            if s and s["v2_flag"]>0:
                out.append({
                    "symbol":sym,"entry_i":t,"entry_date":rows[t]["date"],"entry":rows[t]["close"],
                    "liquidity":c["median_base_value"],"resistance":c["base_high"],
                    "breadth20":s["market_breadth20"],"market5":s["market5_ret"],"market20":s["market20_ret"],
                    "rs20":s["rs20"],"breakout_close":rows[t]["close"],
                })
            nxt=t+11
        t+=1
    return out

def base_outcome(rows,s):
    e=s["entry"]; tgt=e*(1+TARGET); stp=e*(1-STOP); fut=rows[s["entry_i"]+1:s["entry_i"]+1+HORIZON]
    if len(fut)<HORIZON:return None
    for h,d in enumerate(fut,1):
        if d["low"]<=stp:
            return {"exit_date":d["date"],"exit_price":stp,"gross_return":-STOP,"exit_type":"stop","holding":h}
        if d["high"]>=tgt:
            return {"exit_date":d["date"],"exit_price":tgt,"gross_return":TARGET,"exit_type":"target","holding":h}
    d=fut[-1]
    return {"exit_date":d["date"],"exit_price":d["close"],"gross_return":d["close"]/e-1,"exit_type":"timeout","holding":HORIZON}

def early_path(rows,s):
    e=s["entry"]; vals=[]; max_hi=e; min_lo=e
    for k in (1,2,3):
        if s["entry_i"]+k>=len(rows):break
        d=rows[s["entry_i"]+k]; max_hi=max(max_hi,d["high"]); min_lo=min(min_lo,d["low"])
        vals.append({
            "day":k,"date":d["date"],"close_ret":d["close"]/e-1,
            "mfe":max_hi/e-1,"mae":min_lo/e-1,
            "close_above_breakout":d["close"]>=s["breakout_close"],
            "close_above_resistance":d["close"]>=s["resistance"],
        })
    return vals

def managed_outcome(rows,s,cfg):
    e=s["entry"]; tgt=e*(1+TARGET); stp=e*(1-STOP); max_hi=e
    fut=rows[s["entry_i"]+1:s["entry_i"]+1+HORIZON]
    if len(fut)<HORIZON:return None
    for h,d in enumerate(fut,1):
        if d["low"]<=stp:
            return {"exit_date":d["date"],"exit_price":stp,"gross_return":-STOP,"exit_type":"stop","holding":h,"early_exit":False}
        if d["high"]>=tgt:
            return {"exit_date":d["date"],"exit_price":tgt,"gross_return":TARGET,"exit_type":"target","holding":h,"early_exit":False}
        max_hi=max(max_hi,d["high"])
        if h==cfg["check_day"]:
            close_ret=d["close"]/e-1; mfe=max_hi/e-1
            if cfg["mode"]=="close_only":
                fail=close_ret<=cfg["close_threshold"]
            elif cfg["mode"]=="close_and_low_mfe":
                fail=close_ret<=cfg["close_threshold"] and mfe<=cfg["mfe_threshold"]
            else:
                fail=d["close"]<s["breakout_close"] and close_ret<=cfg["close_threshold"]
            if fail:
                return {"exit_date":d["date"],"exit_price":d["close"],"gross_return":close_ret,"exit_type":"early_failure","holding":h,"early_exit":True}
    d=fut[-1]
    return {"exit_date":d["date"],"exit_price":d["close"],"gross_return":d["close"]/e-1,"exit_type":"timeout","holding":HORIZON,"early_exit":False}

def build_trades(signals,data,cfg=None):
    out=[]
    for s in signals:
        o=base_outcome(data[s["symbol"]],s) if cfg is None else managed_outcome(data[s["symbol"]],s,cfg)
        if not o:continue
        out.append({**o,"symbol":s["symbol"],"entry":s["entry"],"entry_date":s["entry_date"],"liquidity":s["liquidity"]})
    return out

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
        pv=0
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
            real.append({"symbol":s,"entry_date":q["entry_date"],"exit_date":d,"net_return":proceeds/q["budget"]-1,"exit_type":tr["exit_type"],"holding":tr["holding"]})
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
    return {"trades":len(real),"skipped":sum(skip.values()),"skip_reasons":dict(skip),"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,"max_drawdown":mdd,"dd_peak":pd,"dd_trough":td,"avg_trade_return":mean(rs),"positive_trade_rate":sum(x>0 for x in rs)/len(rs) if rs else 0,"early_exits":sum(x["exit_type"]=="early_failure" for x in real),"weekly":weekly(curve),"avg_exposure":mean([x["exposure"] for x in curve]),"curve":curve,"realized":real}

def slim(x):return {k:v for k,v in x.items() if k not in {"curve","realized"}}

def path_diag(signals,data,period):
    groups={"target":[],"stop":[],"timeout":[]}
    for s in signals:
        if not in_period(s["entry_date"],period):continue
        o=base_outcome(data[s["symbol"]],s)
        if not o:continue
        groups[o["exit_type"]].append(early_path(data[s["symbol"]],s))
    out={}
    for typ,arr in groups.items():
        d=[]
        for day in (1,2,3):
            rows=[next((x for x in p if x["day"]==day),None) for p in arr]
            rows=[x for x in rows if x]
            d.append({
                "day":day,"n":len(rows),
                "avg_close_ret":mean([x["close_ret"] for x in rows]),
                "avg_mfe":mean([x["mfe"] for x in rows]),
                "avg_mae":mean([x["mae"] for x in rows]),
                "pct_close_below_entry":sum(x["close_ret"]<0 for x in rows)/len(rows) if rows else None,
                "pct_close_below_breakout":sum(not x["close_above_breakout"] for x in rows)/len(rows) if rows else None,
            })
        out[typ]={"trades":len(arr),"days":d}
    return out

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw"); files=sorted(glob.glob(os.path.join(root,"*","*.csv"))); data={}
    for fp in files:
        s=os.path.basename(fp).split(".")[0].upper(); rows=v3.load_csv_all(fp)
        if len(rows)>=100:data[s]=rows
    market=v3.build_market_maps(data); signals=[]
    for s,rows in data.items():signals+=collect(s,rows,market)
    baseline=build_trades(signals,data,None)
    b23=simulate(baseline,data,VAL1); b24=simulate(baseline,data,VAL2); bf=simulate(baseline,data,FINAL)

    diagnostics={"train_2021_2022":path_diag(signals,data,TRAIN),"2023":path_diag(signals,data,VAL1),"2024":path_diag(signals,data,VAL2),"final_research_period":path_diag(signals,data,FINAL)}

    eligible=[]; near=[]; tested=0
    for day in CHECK_DAYS:
      for ct in CLOSE_THRESHOLDS:
       for mt in MFE_THRESHOLDS:
        for mode in MODE:
            if mode!="close_and_low_mfe" and mt!=MFE_THRESHOLDS[0]:
                continue
            tested+=1
            cfg={"check_day":day,"close_threshold":ct,"mfe_threshold":mt,"mode":mode}
            tr=build_trades(signals,data,cfg); a=simulate(tr,data,VAL1); b=simulate(tr,data,VAL2)
            if a["trades"]<MIN_TRADES or b["trades"]<MIN_TRADES:continue
            wr1=(1+a["total_return"])/(1+b23["total_return"]); wr2=(1+b["total_return"])/(1+b24["total_return"])
            dr1=1-abs(a["max_drawdown"])/abs(b23["max_drawdown"]); dr2=1-abs(b["max_drawdown"])/abs(b24["max_drawdown"])
            ar1=a["weekly"]["active_ge_2_rate"]/b23["weekly"]["active_ge_2_rate"] if b23["weekly"]["active_ge_2_rate"] else 1
            ar2=b["weekly"]["active_ge_2_rate"]/b24["weekly"]["active_ge_2_rate"] if b24["weekly"]["active_ge_2_rate"] else 1
            row={"config":cfg,"2023":slim(a),"2024":slim(b),"min_wealth_ratio":min(wr1,wr2),"min_dd_reduction":min(dr1,dr2),"min_active_ge2_ratio":min(ar1,ar2),"min_cagr":min(a["cagr"],b["cagr"])}
            near.append(row)
            if row["min_wealth_ratio"]>=MIN_WEALTH_RATIO and row["min_dd_reduction"]>=MIN_DD_REDUCTION and row["min_active_ge2_ratio"]>=MIN_ACTIVE_GE2_RATIO:
                eligible.append(row)
    eligible.sort(key=lambda z:(z["min_wealth_ratio"],z["min_dd_reduction"],z["min_active_ge2_ratio"],z["min_cagr"]),reverse=True)
    near.sort(key=lambda z:(z["min_wealth_ratio"],z["min_dd_reduction"],z["min_active_ge2_ratio"]),reverse=True)
    best=eligible[0] if eligible else None
    fin=simulate(build_trades(signals,data,best["config"]),data,FINAL) if best else None
    result={
        "pattern":"Defensive Lift v5.6 Early Path Behavior",
        "goal":"test whether early post-breakout price behavior can detect failures before -4.5% stop without cutting the right tail",
        "fixed":{"entry":"frozen v2 DLP","target":TARGET,"stop":STOP,"horizon":HORIZON,"slots":SLOTS,"slot_size":0.5,"friction_round_trip":FRICTION,"ranking":"v3.2 liquidity"},
        "protocol":{"diagnostic_train":TRAIN,"validation_2023":VAL1,"validation_2024":VAL2,"final_research_period":FINAL,"final_not_used_for_selection":True,"min_wealth_ratio_each_validation":MIN_WEALTH_RATIO,"min_dd_reduction_each_validation":MIN_DD_REDUCTION,"min_active_ge2_ratio_each_validation":MIN_ACTIVE_GE2_RATIO},
        "dataset":{"stocks":len(data),"signals":len(signals)},
        "path_diagnostics":diagnostics,
        "baseline_v32":{"2023":slim(b23),"2024":slim(b24),"final":slim(bf)},
        "grid":{"check_days":CHECK_DAYS,"close_thresholds":CLOSE_THRESHOLDS,"mfe_thresholds":MFE_THRESHOLDS,"modes":MODE,"tested":tested,"eligible":len(eligible)},
        "selected":best,"final_result":slim(fin) if fin else None,"top20":eligible[:20],"best_near_misses":near[:20],
    }
    if fin:
        result["comparison_final"]={"wealth_ratio":(1+fin["total_return"])/(1+bf["total_return"]),"drawdown_reduction":1-abs(fin["max_drawdown"])/abs(bf["max_drawdown"]),"return_change_pp":100*(fin["total_return"]-bf["total_return"]),"active_ge2_rate_ratio":fin["weekly"]["active_ge_2_rate"]/bf["weekly"]["active_ge_2_rate"] if bf["weekly"]["active_ge_2_rate"] else None}
    with open("tmp/egx_backtest/results_v56_early_path_behavior.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result.get(k) for k in ["pattern","protocol","dataset","path_diagnostics","baseline_v32","grid","selected","final_result","comparison_final","best_near_misses"]},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
