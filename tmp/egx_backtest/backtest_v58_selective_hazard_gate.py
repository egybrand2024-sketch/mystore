import glob,json,os,sys
from collections import defaultdict
from datetime import datetime,timedelta

sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3

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

# v5.8 is deliberately selective: normal DLP signals keep the full 50% v3.2 entry.
# Only pre-entry hazardous signals receive staged protection.
HAZARD_MODES=[
    "context_plus_one_tech",
    "context_plus_two_tech",
    "weak_breadth_plus_one_tech",
    "double_context_plus_one_tech",
]
PROBE_FRACS=[0.30,0.35,0.40,0.45]
CONFIRM_MODES=["close_ge_entry","mfe_ge_2pct","close_ge_entry_and_mfe_ge_2pct"]
UNCONFIRMED_ACTIONS=["hold_probe","exit_probe"]
ADD_DAY=1

# Fixed interpretable hazard flags, chosen before validation grid evaluation.
BREADTH_WEAK=0.40
MARKET20_WEAK=-0.02
RS20_WEAK=0.0
BREAKOUT_EXTENDED=0.04
OVERHEAD_TIGHT=0.03

MIN_WEALTH_RATIO=0.98
MIN_DD_REDUCTION=0.10
MIN_ACTIVE_GE2_RATIO=0.95
MAX_HAZARD_SHARE=0.35
MIN_TRADES=12


def week_start(s):
    d=datetime.fromisoformat(s).date()
    return (d-timedelta(days=(d.weekday()+1)%7)).isoformat()

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
        "active_weeks":len(active),"active_avg":mean(active),
        "active_ge_2_rate":sum(x>=WEEKLY_TARGET for x in active)/len(active) if active else 0,
        "weekend_ge_2_rate":sum(x>=WEEKLY_TARGET for x in vals)/len(vals) if vals else 0,
        "hit_2_anytime_rate":hit_any/len(vals) if vals else 0,
        "worst":min(vals) if vals else 0,"best":max(vals) if vals else 0,
    }

def collect(sym,rows,market):
    out=[]; nxt=60; t=60
    while t < len(rows)-HORIZON:
        if t<nxt:
            t+=1; continue
        matches=[]
        for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
            c=v3.v1_candidate(rows,t,n)
            if c: matches.append(c)
        if matches:
            c=max(matches,key=lambda x:x["base_n"])
            s=v3.make_signal(sym,rows,t,c,market)
            if s and s["v2_flag"]>0:
                out.append({
                    "symbol":sym,"entry_i":t,"entry_date":rows[t]["date"],"entry":rows[t]["close"],
                    "liquidity":c["median_base_value"],"resistance":c["base_high"],
                    "breadth20":s["market_breadth20"],"market5":s["market5_ret"],"market20":s["market20_ret"],
                    "rs20":s["rs20"],"breakout_ret":s["breakout_ret"],
                    "nearest_overhead":s["nearest_overhead_pct"],"breakout_vol_ratio":s["breakout_vol_ratio"],
                    "clv":s["clv"],"body":s["body"],
                })
            nxt=t+11
        t+=1
    return out

def base_outcome(rows,s):
    e=s["entry"]; tgt=e*(1+TARGET); stp=e*(1-STOP)
    fut=rows[s["entry_i"]+1:s["entry_i"]+1+HORIZON]
    if len(fut)<HORIZON:return None
    for h,d in enumerate(fut,1):
        # Conservative same-bar ambiguity: stop first.
        if d["low"]<=stp:
            return {"exit_date":d["date"],"exit_price":stp,"gross_return":-STOP,"exit_type":"stop","holding":h}
        if d["high"]>=tgt:
            return {"exit_date":d["date"],"exit_price":tgt,"gross_return":TARGET,"exit_type":"target","holding":h}
    d=fut[-1]
    return {"exit_date":d["date"],"exit_price":d["close"],"gross_return":d["close"]/e-1,"exit_type":"timeout","holding":HORIZON}

def build_signal_trades(data):
    market=v3.build_market_maps(data); signals=[]; trades=[]
    for sym,rows in data.items():
        signals+=collect(sym,rows,market)
    for s in signals:
        o=base_outcome(data[s["symbol"]],s)
        if o: trades.append({**s,**o})
    return trades,signals

def hazard_flags(tr):
    flags={
        "weak_breadth":tr["breadth20"]<=BREADTH_WEAK,
        "weak_market20":tr["market20"]<=MARKET20_WEAK,
        "weak_rs20":tr["rs20"]<=RS20_WEAK,
        "extended_breakout":tr["breakout_ret"]>=BREAKOUT_EXTENDED,
        "tight_overhead":tr["nearest_overhead"]<=OVERHEAD_TIGHT,
    }
    return flags

def is_hazard(tr,mode):
    f=hazard_flags(tr)
    context=f["weak_breadth"] or f["weak_market20"]
    tech=sum([f["weak_rs20"],f["extended_breakout"],f["tight_overhead"]])
    if mode=="context_plus_one_tech": return context and tech>=1
    if mode=="context_plus_two_tech": return context and tech>=2
    if mode=="weak_breadth_plus_one_tech": return f["weak_breadth"] and tech>=1
    if mode=="double_context_plus_one_tech": return f["weak_breadth"] and f["weak_market20"] and tech>=1
    raise ValueError(mode)

def hazard_profile(trades,mode):
    hz=[t for t in trades if is_hazard(t,mode)]; nh=[t for t in trades if not is_hazard(t,mode)]
    def one(arr):
        return {
            "n":len(arr),
            "target_rate":sum(t["exit_type"]=="target" for t in arr)/len(arr) if arr else 0,
            "stop_rate":sum(t["exit_type"]=="stop" for t in arr)/len(arr) if arr else 0,
            "avg_gross":mean([t["gross_return"] for t in arr]),
        }
    return {"hazard":one(hz),"non_hazard":one(nh),"hazard_share":len(hz)/len(trades) if trades else 0}

def confirm(rows,entry_i,mode,entry):
    j=entry_i+ADD_DAY
    if j>=len(rows): return False,None
    sub=rows[entry_i+1:j+1]; close=rows[j]["close"]
    mfe=max(x["high"]/entry-1 for x in sub) if sub else 0
    if mode=="close_ge_entry": ok=close>=entry
    elif mode=="mfe_ge_2pct": ok=mfe>=0.02
    elif mode=="close_ge_entry_and_mfe_ge_2pct": ok=(close>=entry and mfe>=0.02)
    else: raise ValueError(mode)
    return ok,{"close_ret":close/entry-1,"mfe":mfe}

def simulate(base_trades,data,period,cfg=None):
    dates=sorted({r["date"] for rows in data.values() for r in rows if period[0]<=r["date"]<=period[1]})
    closes={s:{r["date"]:r["close"] for r in rows} for s,rows in data.items()}
    highs={s:{r["date"]:r["high"] for r in rows} for s,rows in data.items()}
    lows={s:{r["date"]:r["low"] for r in rows} for s,rows in data.items()}
    idxmap={s:{r["date"]:i for i,r in enumerate(rows)} for s,rows in data.items()}
    eb=defaultdict(list)
    for tr in base_trades:
        if period[0]<=tr["entry_date"]<=period[1] and tr["exit_date"]<=period[1]:
            eb[tr["entry_date"]].append(tr)
    for d in eb: eb[d].sort(key=lambda x:(-x["liquidity"],x["symbol"]))

    cash=INITIAL; pos={}; last={}; curve=[]; real=[]; skip=defaultdict(int); half=FRICTION/2
    hazard_entries=0; protected_entries=0; hazard_confirmed=0; hazard_unconfirmed=0; hazard_stop_before_confirm=0; hazard_target_before_confirm=0

    def mark(d):
        pv=0
        for s,q in pos.items():
            px=closes.get(s,{}).get(d,last.get(s,q["entry"]))
            if px is not None:last[s]=px
            pv+=q["shares"]*last[s]
        return cash+pv,pv

    for d in dates:
        # Manage existing positions first. Intraday stop/target is evaluated before close-based confirmation.
        for s in list(pos):
            q=pos[s]; px=closes[s].get(d)
            if px is None: continue
            last[s]=px
            if d==q["entry_date"]: continue
            q["age"]+=1
            stop_px=q["anchor_entry"]*(1-STOP); target_px=q["anchor_entry"]*(1+TARGET)
            exit_type=None; exit_px=None
            if lows[s][d]<=stop_px:
                exit_type="stop"; exit_px=stop_px
                if q["hazard"] and not q["stage_decided"]: hazard_stop_before_confirm+=1
            elif highs[s][d]>=target_px:
                exit_type="target"; exit_px=target_px
                if q["hazard"] and not q["stage_decided"]: hazard_target_before_confirm+=1
            elif q["age"]>=HORIZON:
                exit_type="timeout"; exit_px=px

            if cfg and q["hazard"] and not q["stage_decided"] and q["age"]>=ADD_DAY and exit_type is None:
                rows=data[s]; ok,diag=confirm(rows,q["entry_index"],cfg["confirm_mode"],q["anchor_entry"])
                q["stage_decided"]=True; q["confirm_diag"]=diag; q["confirmed"]=ok
                if ok:
                    hazard_confirmed+=1
                    eq,_=mark(d); target_budget=eq*0.50
                    add_budget=max(0,min(target_budget-q["budget"],cash))
                    if add_budget>1:
                        invested=add_budget*(1-half); add_sh=invested/px; cash-=add_budget
                        q["shares"]+=add_sh; q["budget"]+=add_budget; q["added"]=True; q["add_date"]=d; q["add_price"]=px
                else:
                    hazard_unconfirmed+=1
                    if cfg["unconfirmed_action"]=="exit_probe":
                        exit_type="early_unconfirmed"; exit_px=px

            if exit_type:
                proceeds=q["shares"]*exit_px*(1-half); cash+=proceeds
                real.append({
                    "symbol":s,"entry_date":q["entry_date"],"exit_date":d,"exit_type":exit_type,
                    "net_return":proceeds/q["budget"]-1,"hazard":q["hazard"],
                    "confirmed":q.get("confirmed",False),"added":q.get("added",False),"probe_frac":q.get("probe_frac",0.50)
                })
                pos.pop(s)

        for tr in eb.get(d,[]):
            s=tr["symbol"]
            if s in pos: skip["duplicate_symbol"]+=1; continue
            if len(pos)>=SLOTS: skip["max_positions"]+=1; continue
            hz=(cfg is not None and is_hazard(tr,cfg["hazard_mode"]))
            if hz: hazard_entries+=1
            eq,_=mark(d)
            frac=cfg["probe_frac"] if hz else 0.50
            budget=min(eq*frac,cash)
            if budget<=1: skip["cash"]+=1; continue
            shares=budget*(1-half)/tr["entry"]; cash-=budget
            pos[s]={
                "shares":shares,"budget":budget,"entry":tr["entry"],"anchor_entry":tr["entry"],
                "entry_date":d,"entry_index":idxmap[s][d],"age":0,"hazard":hz,
                "stage_decided":not hz,"confirmed":not hz,"added":False,"probe_frac":frac,
            }
            if hz: protected_entries+=1
            last[s]=tr["entry"]

        eq,pv=mark(d)
        curve.append({"date":d,"equity":eq,"open":len(pos),"exposure":pv/eq if eq else 0})

    mdd,pd,td=maxdd(curve); final=curve[-1]["equity"]
    d0=datetime.fromisoformat(curve[0]["date"]).date(); d1=datetime.fromisoformat(curve[-1]["date"]).date()
    yrs=max((d1-d0).days/365.25,1/365.25); rs=[x["net_return"] for x in real]
    return {
        "trades":len(real),"skipped":sum(skip.values()),"skip_reasons":dict(skip),
        "final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,
        "max_drawdown":mdd,"dd_peak":pd,"dd_trough":td,
        "avg_trade_return":mean(rs),"positive_trade_rate":sum(x>0 for x in rs)/len(rs) if rs else 0,
        "weekly":weekly(curve),"avg_exposure":mean([x["exposure"] for x in curve]),
        "hazard_runtime":{
            "hazard_entries":hazard_entries,"protected_entries":protected_entries,
            "confirmed":hazard_confirmed,"unconfirmed":hazard_unconfirmed,
            "stop_before_confirmation":hazard_stop_before_confirm,"target_before_confirmation":hazard_target_before_confirm,
        },
        "realized":real,"curve":curve,
    }

def slim(x): return {k:v for k,v in x.items() if k not in {"realized","curve"}}

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw"); data={}
    for fp in sorted(glob.glob(os.path.join(root,"*","*.csv"))):
        s=os.path.basename(fp).split(".")[0].upper(); rows=v3.load_csv_all(fp)
        if len(rows)>=100:data[s]=rows
    trades,signals=build_signal_trades(data)
    def per(p): return [t for t in trades if p[0]<=t["entry_date"]<=p[1] and t["exit_date"]<=p[1]]

    t23=per(VAL1); t24=per(VAL2); tf=per(FINAL)
    b23=simulate(t23,data,VAL1,None); b24=simulate(t24,data,VAL2,None); bf=simulate(tf,data,FINAL,None)

    profiles={}
    for hm in HAZARD_MODES:
        profiles[hm]={"2023":hazard_profile(t23,hm),"2024":hazard_profile(t24,hm),"final_research_period":hazard_profile(tf,hm)}

    tested=0; eligible=[]; allrows=[]
    for hm in HAZARD_MODES:
      for pf in PROBE_FRACS:
       for cm in CONFIRM_MODES:
        for ua in UNCONFIRMED_ACTIONS:
          tested+=1
          cfg={"hazard_mode":hm,"probe_frac":pf,"confirm_mode":cm,"unconfirmed_action":ua}
          a=simulate(t23,data,VAL1,cfg); b=simulate(t24,data,VAL2,cfg)
          if a["trades"]<MIN_TRADES or b["trades"]<MIN_TRADES: continue
          wr1=(1+a["total_return"])/(1+b23["total_return"]); wr2=(1+b["total_return"])/(1+b24["total_return"])
          dr1=1-abs(a["max_drawdown"])/abs(b23["max_drawdown"]); dr2=1-abs(b["max_drawdown"])/abs(b24["max_drawdown"])
          ar1=a["weekly"]["active_ge_2_rate"]/b23["weekly"]["active_ge_2_rate"] if b23["weekly"]["active_ge_2_rate"] else 1
          ar2=b["weekly"]["active_ge_2_rate"]/b24["weekly"]["active_ge_2_rate"] if b24["weekly"]["active_ge_2_rate"] else 1
          hp1=profiles[hm]["2023"]["hazard_share"]; hp2=profiles[hm]["2024"]["hazard_share"]
          row={
              "config":cfg,"2023":slim(a),"2024":slim(b),
              "hazard_profile_2023":profiles[hm]["2023"],"hazard_profile_2024":profiles[hm]["2024"],
              "min_wealth_ratio":min(wr1,wr2),"min_dd_reduction":min(dr1,dr2),
              "min_active_ge2_ratio":min(ar1,ar2),"max_hazard_share":max(hp1,hp2),"min_cagr":min(a["cagr"],b["cagr"]),
          }
          allrows.append(row)
          if (row["min_wealth_ratio"]>=MIN_WEALTH_RATIO and row["min_dd_reduction"]>=MIN_DD_REDUCTION
              and row["min_active_ge2_ratio"]>=MIN_ACTIVE_GE2_RATIO and row["max_hazard_share"]<=MAX_HAZARD_SHARE):
              eligible.append(row)

    eligible.sort(key=lambda z:(z["min_wealth_ratio"],z["min_dd_reduction"],z["min_active_ge2_ratio"],-z["max_hazard_share"],z["min_cagr"]),reverse=True)
    allrows.sort(key=lambda z:(z["min_wealth_ratio"],z["min_dd_reduction"],z["min_active_ge2_ratio"],-z["max_hazard_share"]),reverse=True)
    best=eligible[0] if eligible else None
    fin=simulate(tf,data,FINAL,best["config"]) if best else None

    result={
        "pattern":"Defensive Lift v5.8 Selective Hazard Gate",
        "goal":"leave normal v3.2 DLP entries untouched at 50%, while applying staged protection only to a small pre-entry hazard subset",
        "fixed":{
            "entry":"frozen v2 DLP","target":TARGET,"stop":STOP,"horizon":HORIZON,
            "max_positions":SLOTS,"normal_slot_size":0.50,"friction_round_trip":FRICTION,"ranking":"v3.2 liquidity",
        },
        "hazard_flags":{
            "weak_breadth":f"breadth20 <= {BREADTH_WEAK}","weak_market20":f"market20 <= {MARKET20_WEAK}",
            "weak_rs20":f"rs20 <= {RS20_WEAK}","extended_breakout":f"breakout_ret >= {BREAKOUT_EXTENDED}",
            "tight_overhead":f"nearest_overhead <= {OVERHEAD_TIGHT}",
        },
        "protocol":{
            "validation_2023":VAL1,"validation_2024":VAL2,"final_research_period":FINAL,"final_not_used_for_selection":True,
            "min_wealth_ratio_each_validation":MIN_WEALTH_RATIO,"min_dd_reduction_each_validation":MIN_DD_REDUCTION,
            "min_active_ge2_ratio_each_validation":MIN_ACTIVE_GE2_RATIO,"max_hazard_share_each_validation":MAX_HAZARD_SHARE,
        },
        "dataset":{"stocks":len(data),"signals":len(signals)},
        "baseline_v32":{"2023":slim(b23),"2024":slim(b24),"final":slim(bf)},
        "hazard_profiles":profiles,
        "grid":{
            "hazard_modes":HAZARD_MODES,"probe_fracs":PROBE_FRACS,"add_day":ADD_DAY,
            "confirm_modes":CONFIRM_MODES,"unconfirmed_actions":UNCONFIRMED_ACTIONS,
            "tested":tested,"eligible":len(eligible),
        },
        "selected":best,"final_result":slim(fin) if fin else None,
        "top20":eligible[:20],"best_near_misses":allrows[:20],
    }
    if fin:
        result["comparison_final"]={
            "wealth_ratio":(1+fin["total_return"])/(1+bf["total_return"]),
            "drawdown_reduction":1-abs(fin["max_drawdown"])/abs(bf["max_drawdown"]),
            "return_change_pp":100*(fin["total_return"]-bf["total_return"]),
            "dd_change_pp":100*(abs(bf["max_drawdown"])-abs(fin["max_drawdown"])),
            "active_ge2_rate_ratio":fin["weekly"]["active_ge_2_rate"]/bf["weekly"]["active_ge_2_rate"] if bf["weekly"]["active_ge_2_rate"] else None,
            "hazard_profile_final":profiles[best["config"]["hazard_mode"]]["final_research_period"],
        }
    with open("tmp/egx_backtest/results_v58_selective_hazard_gate.json","w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({
        "pattern":result["pattern"],"protocol":result["protocol"],"dataset":result["dataset"],
        "baseline_v32":result["baseline_v32"],"hazard_profiles":result["hazard_profiles"],
        "grid":result["grid"],"selected":result["selected"],"final_result":result["final_result"],
        "comparison_final":result.get("comparison_final"),"best_near_misses":result["best_near_misses"][:5],
    },ensure_ascii=False,indent=2))

if __name__=="__main__": main()
