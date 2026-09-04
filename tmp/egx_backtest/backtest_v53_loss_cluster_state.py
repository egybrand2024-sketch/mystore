import glob,json,os,sys
from collections import defaultdict
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

AMBER_TTLS=[3,5]
CLUSTER_WINDOWS=[5,10]
RED_TTLS=[3,5]
MARKET5_THRESH=[-0.02,0.0]
BREADTH_THRESH=[0.45,0.50]
WEAK_MODES=["and","or"]
OPEN_PAIN_THRESH=[-0.03,-0.02]
BLOCK_AMBER=[False,True]

MIN_WEALTH_RATIO=0.97
MIN_DD_REDUCTION=0.10
MIN_ACTIVE_GE2_RATIO=0.90
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
    for r in curve:
        by[week_start(r["date"])].append(r)
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
        "weeks":len(vals),
        "avg":avg(vals),
        "positive_rate":sum(x>0 for x in vals)/len(vals) if vals else 0,
        "weekend_ge_2_rate":sum(x>=WEEKLY_TARGET for x in vals)/len(vals) if vals else 0,
        "hit_2_anytime_rate":hit_any/len(vals) if vals else 0,
        "active_weeks":len(active),
        "active_avg":avg(active),
        "active_positive_rate":sum(x>0 for x in active)/len(active) if active else 0,
        "active_ge_2_rate":sum(x>=WEEKLY_TARGET for x in active)/len(active) if active else 0,
        "worst":min(vals) if vals else 0,
        "best":max(vals) if vals else 0,
    }

def build_maps(data):
    closes={}; dates=set()
    for s,rows in data.items():
        closes[s]={r["date"]:r["close"] for r in rows}
        dates.update(closes[s])
    return closes,sorted(dates)

def market_is_weak(d,market,cfg):
    m5=market["m5"].get(d,0.0)
    b=market["breadth20"].get(d,0.5)
    a=m5<=cfg["market5_thresh"]
    c=b<=cfg["breadth_thresh"]
    return (a and c) if cfg["weak_mode"]=="and" else (a or c),m5,b

def current_state(i,amber_until,red_until):
    if i<=red_until: return "RED"
    if i<=amber_until: return "AMBER"
    return "GREEN"

def simulate(trades,data,market,period,cfg=None):
    closes,all_dates=build_maps(data)
    dates=[d for d in all_dates if period[0]<=d<=period[1]]
    idx={d:i for i,d in enumerate(dates)}
    eb=defaultdict(list); xb=defaultdict(list)
    for t in trades:
        eb[t["entry_date"]].append(t); xb[t["exit_date"]].append(t)
    for d in eb:
        eb[d].sort(key=lambda x:(-x["liquidity"],x["symbol"]))

    half=FRICTION/2; cash=INITIAL; pos={}; last={}; curve=[]; realized=[]; skip=defaultdict(int)
    amber_until=-1; red_until=-1; last_loss_i=-10**9
    state_days=defaultdict(int); entry_states=defaultdict(int); transitions=[]

    def mark(d):
        pv=0
        for s,q in pos.items():
            px=closes.get(s,{}).get(d)
            if px is not None: last[s]=px
            pv+=q["shares"]*last.get(s,q["entry"])
        return cash+pv,pv

    for d in dates:
        i=idx[d]
        for s in list(pos):
            px=closes.get(s,{}).get(d)
            if px is not None: last[s]=px

        weak,m5,breadth=market_is_weak(d,market,cfg) if cfg else (False,market["m5"].get(d,0.0),market["breadth20"].get(d,0.5))

        # Exits happen before same-day new entries. Realized losses may change state immediately.
        for tr in sorted(xb.get(d,[]),key=lambda x:x["symbol"]):
            s=tr["symbol"]
            if s not in pos: continue
            q=pos.pop(s)
            proceeds=q["shares"]*tr["exit_price"]*(1-half); cash+=proceeds
            net=proceeds/q["budget"]-1
            realized.append({"symbol":s,"entry_date":q["entry_date"],"exit_date":d,"net_return":net,"exit_type":tr["exit_type"],"holding":tr["holding"]})
            if cfg and net<0:
                prev_state=current_state(i,amber_until,red_until)
                clustered=(i-last_loss_i)<=cfg["cluster_window"]
                if clustered:
                    red_until=max(red_until,i+cfg["red_ttl"])
                    amber_until=max(amber_until,red_until+cfg["amber_ttl"])
                else:
                    amber_until=max(amber_until,i+cfg["amber_ttl"])
                last_loss_i=i
                new_state=current_state(i,amber_until,red_until)
                if new_state!=prev_state:
                    transitions.append({"date":d,"from":prev_state,"to":new_state,"reason":"clustered_loss" if clustered else "loss"})

        # Market weakness only escalates risk after a loss has already put the machine in AMBER.
        if cfg:
            st=current_state(i,amber_until,red_until)
            open_pain=False
            for s,q in pos.items():
                px=closes.get(s,{}).get(d,last.get(s,q["entry"]))
                if px/q["entry"]-1 <= cfg["open_pain_thresh"]:
                    open_pain=True; break
            if st=="AMBER" and (weak or open_pain):
                red_until=max(red_until,i+cfg["red_ttl"])
                amber_until=max(amber_until,red_until+cfg["amber_ttl"])
                transitions.append({"date":d,"from":"AMBER","to":"RED","reason":"weak_market" if weak else "open_pain"})

        st=current_state(i,amber_until,red_until) if cfg else "GREEN"
        state_days[st]+=1

        for tr in eb.get(d,[]):
            if tr["symbol"] in pos:
                skip["duplicate_symbol"]+=1; continue
            if len(pos)>=SLOTS:
                skip["max_positions"]+=1; continue
            # Never reduce the first position. State machine only controls whether a second 50% slot may be added.
            if cfg and len(pos)==1:
                if st=="RED":
                    skip["state_red_second_slot"]+=1; continue
                if st=="AMBER" and cfg["block_amber"]:
                    skip["state_amber_second_slot"]+=1; continue
            eq,_=mark(d); budget=min(eq*0.50,cash)
            if budget<=1:
                skip["cash"]+=1; continue
            invested=budget*(1-half); shares=invested/tr["entry"]; cash-=budget
            pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"entry_date":d,"budget":budget}
            last[tr["symbol"]]=tr["entry"]
            entry_states[st]+=1

        eq,pv=mark(d)
        curve.append({"date":d,"equity":eq,"open":len(pos),"exposure":pv/eq if eq else 0,"state":st,"market5":m5,"breadth20":breadth})

    mdd,pd,td=maxdd(curve); final=curve[-1]["equity"]
    d0=datetime.fromisoformat(curve[0]["date"]).date(); d1=datetime.fromisoformat(curve[-1]["date"]).date()
    yrs=max((d1-d0).days/365.25,1/365.25)
    rs=[x["net_return"] for x in realized]
    max_loss_streak=cur=0
    for r in rs:
        if r<0:
            cur+=1; max_loss_streak=max(max_loss_streak,cur)
        else:
            cur=0
    return {
        "trades":len(realized),"skipped":sum(skip.values()),"skip_reasons":dict(skip),
        "final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,
        "max_drawdown":mdd,"dd_peak":pd,"dd_trough":td,
        "avg_trade_return":sum(rs)/len(rs) if rs else 0,
        "positive_trade_rate":sum(x>0 for x in rs)/len(rs) if rs else 0,
        "longest_losing_streak":max_loss_streak,
        "weekly":weekly(curve),
        "avg_exposure":sum(x["exposure"] for x in curve)/len(curve),
        "state_days":dict(state_days),"entry_states":dict(entry_states),
        "transitions":transitions,"curve":curve,"realized":realized,
    }

def slim(x):
    return {k:v for k,v in x.items() if k not in {"transitions","curve","realized"}}

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw")
    files=sorted(glob.glob(os.path.join(root,"*","*.csv"))); data={}
    for fp in files:
        s=os.path.basename(fp).split(".")[0].upper(); r=v3.load_csv_all(fp)
        if len(r)>=100:data[s]=r
    market=v3.build_market_maps(data); raw=[]
    for s,r in data.items(): raw+=v51.collect(s,r,market)
    alltr=[v51.finalize(x) for x in raw]
    def tp(p): return [x for x in alltr if in_period(x["entry_date"],p) and x["exit_date"]<=p[1]]

    b23=simulate(tp(VAL1),data,market,VAL1,None)
    b24=simulate(tp(VAL2),data,market,VAL2,None)
    bf=simulate(tp(FINAL),data,market,FINAL,None)

    ranked=[]; near=[]; tested=0
    for a in AMBER_TTLS:
      for cw in CLUSTER_WINDOWS:
       for rttl in RED_TTLS:
        for mt in MARKET5_THRESH:
         for bt in BREADTH_THRESH:
          for wm in WEAK_MODES:
           for op in OPEN_PAIN_THRESH:
            for ba in BLOCK_AMBER:
                tested+=1
                cfg={"amber_ttl":a,"cluster_window":cw,"red_ttl":rttl,"market5_thresh":mt,"breadth_thresh":bt,"weak_mode":wm,"open_pain_thresh":op,"block_amber":ba}
                x=simulate(tp(VAL1),data,market,VAL1,cfg); y=simulate(tp(VAL2),data,market,VAL2,cfg)
                if x["trades"]<MIN_TRADES or y["trades"]<MIN_TRADES: continue
                wr1=(1+x["total_return"])/(1+b23["total_return"]); wr2=(1+y["total_return"])/(1+b24["total_return"])
                dr1=1-abs(x["max_drawdown"])/abs(b23["max_drawdown"]); dr2=1-abs(y["max_drawdown"])/abs(b24["max_drawdown"])
                ar1=x["weekly"]["active_ge_2_rate"]/b23["weekly"]["active_ge_2_rate"] if b23["weekly"]["active_ge_2_rate"]>0 else 1
                ar2=y["weekly"]["active_ge_2_rate"]/b24["weekly"]["active_ge_2_rate"] if b24["weekly"]["active_ge_2_rate"]>0 else 1
                row={"config":cfg,"2023":slim(x),"2024":slim(y),"min_wealth_ratio":min(wr1,wr2),"min_dd_reduction":min(dr1,dr2),"min_active_ge2_ratio":min(ar1,ar2),"min_cagr":min(x["cagr"],y["cagr"])}
                near.append(row)
                if row["min_wealth_ratio"]>=MIN_WEALTH_RATIO and row["min_dd_reduction"]>=MIN_DD_REDUCTION and row["min_active_ge2_ratio"]>=MIN_ACTIVE_GE2_RATIO:
                    ranked.append(row)

    ranked.sort(key=lambda z:(z["min_wealth_ratio"],z["min_dd_reduction"],z["min_active_ge2_ratio"],z["min_cagr"]),reverse=True)
    near.sort(key=lambda z:(z["min_wealth_ratio"]+z["min_dd_reduction"]+z["min_active_ge2_ratio"],z["min_cagr"]),reverse=True)
    best=ranked[0] if ranked else None
    fin=simulate(tp(FINAL),data,market,FINAL,best["config"]) if best else None

    result={
        "pattern":"Defensive Lift v5.3 Loss-Cluster State Machine",
        "goal":"preserve 50% position size and v3.2 upside while blocking only a second slot during evidence-based loss-cluster states",
        "fixed":{"entry":"frozen v2 DLP","target":TARGET,"stop":STOP,"horizon":HORIZON,"slots":SLOTS,"slot_size":0.50,"friction_round_trip":FRICTION,"ranking":"frozen v3.2 liquidity ranking"},
        "state_machine":{
            "GREEN":"normal; first and second 50% slots allowed",
            "AMBER":"entered after a realized losing trade for a limited number of sessions",
            "RED":"entered after a second loss inside cluster window, or AMBER plus weak market/open-position pain",
            "risk_action":"never resize or force-exit an existing trade; first 50% slot is always allowed; only the second 50% slot may be blocked",
        },
        "protocol":{"validation_2023":VAL1,"validation_2024":VAL2,"final_holdout":FINAL,"final_not_used_for_selection":True,"min_wealth_ratio_vs_v32_each_validation":MIN_WEALTH_RATIO,"min_drawdown_reduction_each_validation":MIN_DD_REDUCTION,"min_active_ge2_rate_ratio_each_validation":MIN_ACTIVE_GE2_RATIO},
        "dataset":{"stocks":len(data),"signals":len(alltr)},
        "baseline_v32":{"2023":slim(b23),"2024":slim(b24),"final":slim(bf)},
        "grid":{"tested":tested,"eligible":len(ranked),"amber_ttl":AMBER_TTLS,"cluster_window":CLUSTER_WINDOWS,"red_ttl":RED_TTLS,"market5_threshold":MARKET5_THRESH,"breadth_threshold":BREADTH_THRESH,"weak_modes":WEAK_MODES,"open_pain_threshold":OPEN_PAIN_THRESH,"block_amber":BLOCK_AMBER},
        "selected":best,
        "final_result":slim(fin) if fin else None,
        "top20":ranked[:20],
        "best_near_misses":near[:20],
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
    with open("tmp/egx_backtest/results_v53_loss_cluster_state.json","w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result.get(k) for k in ["pattern","state_machine","protocol","dataset","baseline_v32","grid","selected","final_result","comparison_final","best_near_misses"]},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
