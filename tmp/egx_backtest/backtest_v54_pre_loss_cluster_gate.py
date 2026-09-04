import glob,json,os,sys
from collections import defaultdict,Counter
from datetime import datetime,timedelta

sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3
import backtest_v51_correlation_risk as v51

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

# Intentionally small rule grid: no ML and no post-loss state.
CROWD_LOOKBACK=[3,5]
CROWD_THRESHOLD=[2,3]
MARKET5_THRESHOLD=[-0.01,0.0]
BREADTH20_THRESHOLD=[0.45,0.50]
OPEN_PAIN_THRESHOLD=[-0.01,0.0]
SCORE_THRESHOLD=[2,3]

MIN_WEALTH_RATIO=0.98
MIN_DD_REDUCTION=0.10
MIN_ACTIVE_GE2_RATIO=0.95
MIN_TRADES=12


def in_period(d,p): return p[0] <= d <= p[1]

def week_start(s):
    d=datetime.fromisoformat(s).date()
    return (d-timedelta(days=(d.weekday()+1)%7)).isoformat()

def maxdd(curve):
    peak=-1; mdd=0; pdate=tdate=None; rp=None
    for r in curve:
        e=r["equity"]
        if e>peak:
            peak=e; rp=r["date"]
        dd=e/peak-1 if peak>0 else 0
        if dd<mdd:
            mdd=dd; pdate=rp; tdate=r["date"]
    return mdd,pdate,tdate

def weekly(curve):
    by=defaultdict(list)
    for r in curve: by[week_start(r["date"])].append(r)
    prev=INITIAL; vals=[]; active=[]; hit_any=0
    for wk in sorted(by):
        arr=by[wk]; end=arr[-1]["equity"]
        ret=end/prev-1 if prev>0 else 0
        vals.append(ret)
        is_active=any(x["exposure"]>1e-9 for x in arr)
        if is_active: active.append(ret)
        mx=max(x["equity"] for x in arr)/prev-1 if prev>0 else 0
        hit_any += mx>=WEEKLY_TARGET
        prev=end
    def avg(x): return sum(x)/len(x) if x else 0
    return {
        "weeks":len(vals),"avg":avg(vals),
        "positive_rate":sum(x>0 for x in vals)/len(vals) if vals else 0,
        "weekend_ge_2_rate":sum(x>=WEEKLY_TARGET for x in vals)/len(vals) if vals else 0,
        "hit_2_anytime_rate":hit_any/len(vals) if vals else 0,
        "active_weeks":len(active),"active_avg":avg(active),
        "active_positive_rate":sum(x>0 for x in active)/len(active) if active else 0,
        "active_ge_2_rate":sum(x>=WEEKLY_TARGET for x in active)/len(active) if active else 0,
        "worst":min(vals) if vals else 0,"best":max(vals) if vals else 0,
    }

def maps(data):
    closes={}; dates=set()
    for s,rows in data.items():
        closes[s]={r["date"]:r["close"] for r in rows}
        dates.update(closes[s])
    return closes,sorted(dates)

def build_signal_counts(alltr,dates):
    by=Counter(t["entry_date"] for t in alltr)
    return {d:by.get(d,0) for d in dates}

def recent_signal_count(d,date_index,dates,signal_counts,lookback):
    i=date_index[d]
    lo=max(0,i-lookback+1)
    return sum(signal_counts.get(dates[j],0) for j in range(lo,i+1))

def gate_score(d,pos,tr,cfg,closes,last,market,date_index,dates,signal_counts):
    reasons=[]
    recent=recent_signal_count(d,date_index,dates,signal_counts,cfg["crowd_lookback"])
    if recent>=cfg["crowd_threshold"]: reasons.append("signal_crowding")
    m5=market["m5"].get(d,0.0)
    if m5<=cfg["market5_threshold"]: reasons.append("weak_market5")
    b20=market["breadth20"].get(d,0.5)
    if b20<=cfg["breadth20_threshold"]: reasons.append("weak_breadth20")
    # The engine only evaluates a second slot, so exactly one position should normally be open here.
    open_ret=None
    if pos:
        s,q=next(iter(pos.items()))
        px=closes.get(s,{}).get(d,last.get(s,q["entry"]))
        open_ret=px/q["entry"]-1 if q["entry"]>0 else 0
        if open_ret<=cfg["open_pain_threshold"]: reasons.append("open_position_pain")
    return len(reasons),reasons,{"recent_signals":recent,"market5":m5,"breadth20":b20,"open_return":open_ret}

def simulate(trades,data,market,period,cfg=None,signal_counts=None):
    closes,all_dates=maps(data)
    dates=[d for d in all_dates if period[0]<=d<=period[1]]
    date_index={d:i for i,d in enumerate(dates)}
    eb=defaultdict(list); xb=defaultdict(list)
    for t in trades:
        eb[t["entry_date"]].append(t); xb[t["exit_date"]].append(t)
    for d in eb: eb[d].sort(key=lambda x:(-x["liquidity"],x["symbol"]))

    half=FRICTION/2; cash=INITIAL; pos={}; last={}; curve=[]; realized=[]
    skip=defaultdict(int); gate_events=[]; reason_counts=Counter()

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
            if s not in pos: continue
            q=pos.pop(s); proceeds=q["shares"]*tr["exit_price"]*(1-half); cash+=proceeds
            net=proceeds/q["budget"]-1
            realized.append({"symbol":s,"entry_date":q["entry_date"],"exit_date":d,"net_return":net,"exit_type":tr["exit_type"],"holding":tr["holding"]})

        for tr in eb.get(d,[]):
            if tr["symbol"] in pos:
                skip["duplicate_symbol"]+=1; continue
            if len(pos)>=SLOTS:
                skip["max_positions"]+=1; continue
            # v5.4 never blocks the first 50% slot. It only evaluates the second slot BEFORE any loss occurs.
            if cfg is not None and len(pos)==1:
                score,reasons,diag=gate_score(d,pos,tr,cfg,closes,last,market,date_index,dates,signal_counts)
                if score>=cfg["score_threshold"]:
                    skip["pre_loss_cluster_gate"]+=1
                    for r in reasons: reason_counts[r]+=1
                    gate_events.append({
                        "date":d,"candidate":tr["symbol"],"score":score,"reasons":reasons,
                        "candidate_gross_return_hindsight":tr["gross_return"],"candidate_exit_type_hindsight":tr["exit_type"],
                        **diag,
                    })
                    continue
            eq,_=mark(d); budget=min(eq*0.50,cash)
            if budget<=1:
                skip["cash"]+=1; continue
            invested=budget*(1-half); shares=invested/tr["entry"]; cash-=budget
            pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"entry_date":d,"budget":budget}
            last[tr["symbol"]]=tr["entry"]

        eq,pv=mark(d)
        curve.append({"date":d,"equity":eq,"open":len(pos),"exposure":pv/eq if eq else 0})

    mdd,pd,td=maxdd(curve); final=curve[-1]["equity"]
    d0=datetime.fromisoformat(curve[0]["date"]).date(); d1=datetime.fromisoformat(curve[-1]["date"]).date()
    yrs=max((d1-d0).days/365.25,1/365.25)
    rs=[x["net_return"] for x in realized]
    blocked_losses=sum(1 for x in gate_events if x["candidate_gross_return_hindsight"]<0)
    blocked_winners=sum(1 for x in gate_events if x["candidate_gross_return_hindsight"]>0)
    blocked_targets=sum(1 for x in gate_events if x["candidate_exit_type_hindsight"]=="target")
    return {
        "trades":len(realized),"skipped":sum(skip.values()),"skip_reasons":dict(skip),
        "final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,
        "max_drawdown":mdd,"dd_peak":pd,"dd_trough":td,
        "avg_trade_return":sum(rs)/len(rs) if rs else 0,
        "positive_trade_rate":sum(x>0 for x in rs)/len(rs) if rs else 0,
        "weekly":weekly(curve),"avg_exposure":sum(x["exposure"] for x in curve)/len(curve),
        "gate_diagnostics":{"events":len(gate_events),"reason_counts":dict(reason_counts),"blocked_losses_hindsight":blocked_losses,"blocked_winners_hindsight":blocked_winners,"blocked_targets_hindsight":blocked_targets},
        "curve":curve,"realized":realized,"gate_events":gate_events,
    }

def slim(x): return {k:v for k,v in x.items() if k not in {"curve","realized","gate_events"}}

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw")
    files=sorted(glob.glob(os.path.join(root,"*","*.csv"))); data={}
    for fp in files:
        s=os.path.basename(fp).split(".")[0].upper(); r=v3.load_csv_all(fp)
        if len(r)>=100:data[s]=r
    market=v3.build_market_maps(data); raw=[]
    for s,r in data.items(): raw+=v51.collect(s,r,market)
    alltr=[v51.finalize(x) for x in raw]
    _,global_dates=maps(data); signal_counts=build_signal_counts(alltr,global_dates)
    def tp(p): return [x for x in alltr if in_period(x["entry_date"],p) and x["exit_date"]<=p[1]]

    b23=simulate(tp(VAL1),data,market,VAL1,None,signal_counts)
    b24=simulate(tp(VAL2),data,market,VAL2,None,signal_counts)
    bf=simulate(tp(FINAL),data,market,FINAL,None,signal_counts)

    eligible=[]; near=[]; tested=0
    for cl in CROWD_LOOKBACK:
      for ct in CROWD_THRESHOLD:
       for mt in MARKET5_THRESHOLD:
        for bt in BREADTH20_THRESHOLD:
         for op in OPEN_PAIN_THRESHOLD:
          for st in SCORE_THRESHOLD:
            tested+=1
            cfg={"crowd_lookback":cl,"crowd_threshold":ct,"market5_threshold":mt,"breadth20_threshold":bt,"open_pain_threshold":op,"score_threshold":st}
            a=simulate(tp(VAL1),data,market,VAL1,cfg,signal_counts)
            b=simulate(tp(VAL2),data,market,VAL2,cfg,signal_counts)
            if a["trades"]<MIN_TRADES or b["trades"]<MIN_TRADES: continue
            wr1=(1+a["total_return"])/(1+b23["total_return"]); wr2=(1+b["total_return"])/(1+b24["total_return"])
            dr1=1-abs(a["max_drawdown"])/abs(b23["max_drawdown"]); dr2=1-abs(b["max_drawdown"])/abs(b24["max_drawdown"])
            ar1=a["weekly"]["active_ge_2_rate"]/b23["weekly"]["active_ge_2_rate"] if b23["weekly"]["active_ge_2_rate"]>0 else 1
            ar2=b["weekly"]["active_ge_2_rate"]/b24["weekly"]["active_ge_2_rate"] if b24["weekly"]["active_ge_2_rate"]>0 else 1
            row={"config":cfg,"2023":slim(a),"2024":slim(b),"min_wealth_ratio":min(wr1,wr2),"min_dd_reduction":min(dr1,dr2),"min_active_ge2_ratio":min(ar1,ar2),"min_cagr":min(a["cagr"],b["cagr"])}
            near.append(row)
            if row["min_wealth_ratio"]>=MIN_WEALTH_RATIO and row["min_dd_reduction"]>=MIN_DD_REDUCTION and row["min_active_ge2_ratio"]>=MIN_ACTIVE_GE2_RATIO:
                eligible.append(row)

    eligible.sort(key=lambda z:(z["min_wealth_ratio"],z["min_dd_reduction"],z["min_active_ge2_ratio"],z["min_cagr"]),reverse=True)
    near.sort(key=lambda z:(z["min_wealth_ratio"],z["min_dd_reduction"],z["min_active_ge2_ratio"]),reverse=True)
    best=eligible[0] if eligible else None
    fin=simulate(tp(FINAL),data,market,FINAL,best["config"],signal_counts) if best else None

    result={
        "pattern":"Defensive Lift v5.4 Pre-Loss Cluster Gate",
        "goal":"detect concentration risk before the first loss and block only the second 50% slot while preserving the first full-size DLP position",
        "fixed":{"entry":"frozen v2 DLP","target":TARGET,"stop":STOP,"horizon":HORIZON,"slots":SLOTS,"slot_size":0.50,"friction_round_trip":FRICTION,"ranking":"frozen v3.2 liquidity ranking"},
        "pre_loss_features":["recent DLP signal crowding","market 5-session impulse","20-session breadth","mark-to-market return of the already-open first position"],
        "risk_action":"no forced exit, no resizing, no post-loss state; first slot always allowed, only second slot can be blocked",
        "protocol":{"validation_2023":VAL1,"validation_2024":VAL2,"final_research_period":FINAL,"final_not_used_for_selection":True,"min_wealth_ratio_vs_v32_each_validation":MIN_WEALTH_RATIO,"min_drawdown_reduction_each_validation":MIN_DD_REDUCTION,"min_active_ge2_rate_ratio_each_validation":MIN_ACTIVE_GE2_RATIO},
        "dataset":{"stocks":len(data),"signals":len(alltr)},
        "baseline_v32":{"2023":slim(b23),"2024":slim(b24),"final":slim(bf)},
        "grid":{"tested":tested,"eligible":len(eligible),"crowd_lookback":CROWD_LOOKBACK,"crowd_threshold":CROWD_THRESHOLD,"market5_threshold":MARKET5_THRESHOLD,"breadth20_threshold":BREADTH20_THRESHOLD,"open_pain_threshold":OPEN_PAIN_THRESHOLD,"score_threshold":SCORE_THRESHOLD},
        "selected":best,"final_result":slim(fin) if fin else None,"top20":eligible[:20],"best_near_misses":near[:20],
    }
    if fin:
        result["comparison_final"]={
            "wealth_ratio":(1+fin["total_return"])/(1+bf["total_return"]),
            "drawdown_reduction":1-abs(fin["max_drawdown"])/abs(bf["max_drawdown"]),
            "return_change_pp":100*(fin["total_return"]-bf["total_return"]),
            "dd_change_pp":100*(abs(bf["max_drawdown"])-abs(fin["max_drawdown"])),
            "active_week_avg_change_pp":100*(fin["weekly"]["active_avg"]-bf["weekly"]["active_avg"]),
            "active_ge2_rate_ratio":fin["weekly"]["active_ge_2_rate"]/bf["weekly"]["active_ge_2_rate"] if bf["weekly"]["active_ge_2_rate"]>0 else None,
        }
    with open("tmp/egx_backtest/results_v54_pre_loss_cluster_gate.json","w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result.get(k) for k in ["pattern","protocol","dataset","baseline_v32","grid","selected","final_result","comparison_final","best_near_misses"]},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
