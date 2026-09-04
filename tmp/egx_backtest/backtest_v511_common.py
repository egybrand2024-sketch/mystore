import glob,json,math,os,sys
from collections import defaultdict
from datetime import datetime
sys.path.insert(0,"tmp/egx_backtest")
import analyze_v58_hazard_attribution as hz
import backtest_v58_selective_hazard_gate as v58

TRAIN=("2021-01-01","2022-12-31")
V23=("2023-01-01","2023-12-31")
V24=("2024-01-01","2024-12-31")
FINAL=("2025-01-01","2026-02-28")
INITIAL=100000.0; TARGET=0.12; STOP=0.045; H=7; SLOTS=2; HALF_FRICTION=0.0025

# Frozen comparison references. v5.10C was selected on 2023/2024 only and never opened on final.
V510C_REF={
    "2023":{"return":0.4003763476700404,"dd":-0.05781411126020031,"active_ge2":0.38461538461538464},
    "2024":{"return":0.48000687652845,"dd":-0.1046462370726311,"active_ge2":0.38461538461538464},
}
V32_FINAL_REF={"return":0.710060075535486,"dd":-0.06909077753849246,"active_ge2":0.37209302325581395}
EPS=1e-12

def q(vals,p): return hz.quantile([x for x in vals if hz.finite(x)],p)
def slim(x): return {k:v for k,v in x.items() if k not in {"curve","realized"}}
def inper(t,p): return p[0]<=t["entry_date"]<=p[1] and t["exit_date"]<=p[1]
def load_data():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw"); data={}
    for fp in sorted(glob.glob(os.path.join(root,"*","*.csv"))):
        s=os.path.basename(fp).split(".")[0].upper(); rows=hz.v3.load_csv_all(fp)
        if len(rows)>=100:data[s]=rows
    return data

def build_context(data):
    trades=hz.build(data)
    train=[t for t in trades if TRAIN[0]<=t["entry_date"]<=TRAIN[1]]
    th={
        "clearance_q75":q([t["clearance"] for t in train],.75),
        "lift_q75":q([t["lift"] for t in train],.75),
        "clearance_q85":q([t["clearance"] for t in train],.85),
        "lift_q85":q([t["lift"] for t in train],.85),
        "clearance_q90":q([t["clearance"] for t in train],.90),
        "lift_q90":q([t["lift"] for t in train],.90),
        "market20_q25":q([t["market20_ret"] for t in train],.25),
        "breadth_q25":q([t["market_breadth20"] for t in train],.25),
    }
    return trades,th

def hazard(t,th):
    return hz.finite(t.get("clearance")) and hz.finite(t.get("lift")) and t["clearance"]>=th["clearance_q75"] and t["lift"]>=th["lift_q75"]
def severe(t,th,level="q85"):
    if level=="q90": return t["clearance"]>=th["clearance_q90"] and t["lift"]>=th["lift_q90"]
    return t["clearance"]>=th["clearance_q85"] and t["lift"]>=th["lift_q85"]
def weak_context(t,th,mode):
    m=t.get("market20_ret"); b=t.get("market_breadth20")
    wm=hz.finite(m) and m<=th["market20_q25"]; wb=hz.finite(b) and b<=th["breadth_q25"]
    if mode=="market20": return wm
    if mode=="breadth": return wb
    if mode=="either": return wm or wb
    if mode=="both": return wm and wb
    if mode=="none": return False
    raise ValueError(mode)

def profile(arr,th):
    x=[t for t in arr if hazard(t,th)]
    return {"n":len(x),"share":len(x)/len(arr) if arr else 0,
            "targets":sum(t["exit_type"]=="target" for t in x),
            "stops":sum(t["exit_type"]=="stop" for t in x),
            "fast_stops":sum(t["exit_type"]=="stop" and t["holding"]<=2 for t in x)}

def make_plan(t,th,family,cfg):
    # Default exact v3.2-like entry for non-hazard signals.
    plan={"hazard":hazard(t,th),"initial_frac":.50,"early_stop":STOP,"stop_days":0,
          "relax_mfe":None,"d1_target":None,"d1_mfe":None,"d1_close":None,
          "d2_target":None,"d2_mfe":None,"d2_close":None,"d3_target":None,"d3_mfe":None,
          "severe":False,"context_weak":False}
    if not plan["hazard"]: return plan
    plan["severe"]=severe(t,th,cfg.get("severe_level","q85"))
    plan["context_weak"]=weak_context(t,th,cfg.get("context_mode","none"))

    if family=="A":
        # Full exposure remains intact; only first-session/first-two-session thesis invalidation is tighter.
        plan.update(initial_frac=.50,early_stop=cfg["early_stop"],stop_days=cfg["stop_days"],relax_mfe=cfg["relax_mfe"])
    elif family=="B":
        # Progressive entry plus temporary early stop. No early discretionary exit.
        plan.update(initial_frac=cfg["initial_frac"],early_stop=cfg["early_stop"],stop_days=cfg["stop_days"],
                    relax_mfe=cfg["relax_mfe"],d1_target=cfg["d1_target"],d1_mfe=cfg["d1_mfe"],d1_close=cfg["d1_close"],
                    d2_target=.50,d2_mfe=cfg.get("d2_mfe",0.0),d2_close=cfg["d2_close"])
    elif family=="C":
        # Severity-tier staging: only the most stretched hazard signals get the smaller initial size.
        plan["initial_frac"]=cfg["severe_frac"] if plan["severe"] else cfg["moderate_frac"]
        plan.update(d1_target=cfg["d1_target"],d1_mfe=cfg["d1_mfe"],d1_close=cfg["d1_close"],
                    d2_target=.50,d2_mfe=0.0,d2_close=cfg["d2_close"])
    elif family=="D":
        # Asymmetric winner pyramid: small initial risk, but confirmed winners may exceed 50% without leverage.
        plan.update(initial_frac=cfg["initial_frac"],d1_target=.50,d1_mfe=cfg["d1_mfe"],d1_close=cfg["d1_close"],
                    d2_target=cfg["pyramid_frac"],d2_mfe=cfg["d2_mfe"],d2_close=cfg["d2_close"])
    elif family=="E":
        # Adaptive hybrid: normal 50% for moderate hazard in good context; protect only severe or weak-context hazards,
        # then allow proven winners to pyramid.
        protect=plan["severe"] or plan["context_weak"]
        if protect:
            plan.update(initial_frac=cfg["protected_frac"],early_stop=cfg["early_stop"],stop_days=cfg["stop_days"],relax_mfe=cfg["relax_mfe"],
                        d1_target=.50,d1_mfe=cfg["d1_mfe"],d1_close=cfg["d1_close"],
                        d2_target=cfg["pyramid_frac"],d2_mfe=cfg["d2_mfe"],d2_close=cfg["d2_close"])
        else:
            plan["initial_frac"]=.50
    else: raise ValueError(family)
    return plan

def simulate(trades,data,period,th,family,cfg):
    dates=sorted({r["date"] for rows in data.values() for r in rows if period[0]<=r["date"]<=period[1]})
    closes={s:{r["date"]:r["close"] for r in rows} for s,rows in data.items()}; highs={s:{r["date"]:r["high"] for r in rows} for s,rows in data.items()}; lows={s:{r["date"]:r["low"] for r in rows} for s,rows in data.items()}
    eb=defaultdict(list)
    for t in trades: eb[t["entry_date"]].append(t)
    for d in eb: eb[d].sort(key=lambda x:(-x["liquidity"],x["symbol"]))
    cash=INITIAL; pos={}; last={}; curve=[]; realized=[]; skipped=defaultdict(int)
    runtime=defaultdict(int)
    def mark(d):
        pv=0.0
        for s,p in pos.items():
            px=closes.get(s,{}).get(d,last.get(s,p["entry"]))
            if px is not None:last[s]=px
            pv+=p["shares"]*last[s]
        return cash+pv,pv
    def add_to_frac(s,p,d,target_frac):
        nonlocal cash
        if target_frac is None:return
        target_budget=p["entry_equity"]*target_frac
        need=max(0.0,target_budget-p["budget"]); add=min(need,cash)
        if add>1:
            px=closes[s][d]; p["shares"]+=add*(1-HALF_FRICTION)/px; p["budget"]+=add; cash-=add; runtime["adds"]+=1
            if target_frac>.50+EPS: runtime["pyramid_adds"]+=1
    for d in dates:
        for s in list(pos):
            p=pos[s]; px=closes[s].get(d)
            if px is None: continue
            last[s]=px
            if d==p["entry_date"]: continue
            p["age"]+=1; age=p["age"]; entry=p["entry"]
            day_mfe=highs[s][d]/entry-1; p["cum_mfe"]=max(p["cum_mfe"],day_mfe)
            # Temporary stop is causal and evaluated intraday before close-based confirmation/adds.
            active_stop=STOP
            if p["plan"]["hazard"] and age<=p["plan"]["stop_days"] and not p["stop_relaxed"]:
                active_stop=p["plan"]["early_stop"]
            stop_px=entry*(1-active_stop); target_px=entry*(1+TARGET)
            exit_type=None; exit_px=None
            if lows[s][d]<=stop_px:
                exit_type="early_stop" if active_stop<STOP-EPS else "stop"; exit_px=stop_px
                runtime[exit_type]+=1
            elif highs[s][d]>=target_px:
                exit_type="target"; exit_px=target_px
            elif age>=H:
                exit_type="timeout"; exit_px=px
            if exit_type:
                proceeds=p["shares"]*exit_px*(1-HALF_FRICTION); cash+=proceeds
                realized.append({"symbol":s,"entry_date":p["entry_date"],"exit_date":d,"exit_type":exit_type,"hazard":p["plan"]["hazard"],"severe":p["plan"]["severe"],"context_weak":p["plan"]["context_weak"],"budget":p["budget"],"net_return":proceeds/p["budget"]-1})
                pos.pop(s); continue
            # Relax temporary stop after sufficient positive excursion.
            rm=p["plan"]["relax_mfe"]
            if rm is not None and p["cum_mfe"]>=rm: p["stop_relaxed"]=True
            close_ret=px/entry-1
            if age==1 and p["plan"]["d1_target"] is not None:
                if p["cum_mfe"]>=p["plan"]["d1_mfe"] and close_ret>=p["plan"]["d1_close"]:
                    add_to_frac(s,p,d,p["plan"]["d1_target"]); runtime["d1_confirms"]+=1
            if age==2 and p["plan"]["d2_target"] is not None:
                if p["cum_mfe"]>=p["plan"]["d2_mfe"] and close_ret>=p["plan"]["d2_close"]:
                    add_to_frac(s,p,d,p["plan"]["d2_target"]); runtime["d2_confirms"]+=1
        for t in eb.get(d,[]):
            s=t["symbol"]
            if s in pos: skipped["duplicate_symbol"]+=1; continue
            if len(pos)>=SLOTS: skipped["max_positions"]+=1; continue
            eq,_=mark(d); plan=make_plan(t,th,family,cfg); budget=min(eq*plan["initial_frac"],cash)
            if budget<=1: skipped["cash"]+=1; continue
            shares=budget*(1-HALF_FRICTION)/t["entry"]; cash-=budget
            pos[s]={"shares":shares,"budget":budget,"entry_equity":eq,"entry":t["entry"],"entry_date":d,"age":0,"cum_mfe":0.0,"stop_relaxed":False,"plan":plan}
            if plan["hazard"]: runtime["hazard_entries"]+=1
            if plan["severe"]: runtime["severe_entries"]+=1
            if plan["context_weak"]: runtime["weak_context_entries"]+=1
            last[s]=t["entry"]
        eq,pv=mark(d); curve.append({"date":d,"equity":eq,"exposure":pv/eq if eq else 0})
    mdd,pd,td=v58.maxdd(curve); final=curve[-1]["equity"]; d0=datetime.fromisoformat(curve[0]["date"]).date(); d1=datetime.fromisoformat(curve[-1]["date"]).date(); yrs=max((d1-d0).days/365.25,1/365.25)
    rs=[r["net_return"] for r in realized]
    return {"trades":len(realized),"skipped":sum(skipped.values()),"skip_reasons":dict(skipped),"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,
            "max_drawdown":mdd,"dd_peak":pd,"dd_trough":td,"avg_trade_return":v58.mean(rs),"positive_trade_rate":sum(x>0 for x in rs)/len(rs) if rs else 0,
            "weekly":v58.weekly(curve),"avg_exposure":v58.mean([x["exposure"] for x in curve]),"runtime":dict(runtime),"realized":realized,"curve":curve}

def validation_score(r23,r24):
    strict=(r23["total_return"]>V510C_REF["2023"]["return"]+EPS and abs(r23["max_drawdown"])<abs(V510C_REF["2023"]["dd"])-EPS and
            r24["total_return"]>V510C_REF["2024"]["return"]+EPS and abs(r24["max_drawdown"])<abs(V510C_REF["2024"]["dd"])-EPS and
            r23["weekly"]["active_ge_2_rate"]>=V510C_REF["2023"]["active_ge2"]-EPS and r24["weekly"]["active_ge_2_rate"]>=V510C_REF["2024"]["active_ge2"]-EPS)
    return {
        "strict_validation_better_than_v510c":strict,
        "return_edge_2023_pp":100*(r23["total_return"]-V510C_REF["2023"]["return"]),
        "return_edge_2024_pp":100*(r24["total_return"]-V510C_REF["2024"]["return"]),
        "dd_improvement_2023_pp":100*(abs(V510C_REF["2023"]["dd"])-abs(r23["max_drawdown"])),
        "dd_improvement_2024_pp":100*(abs(V510C_REF["2024"]["dd"])-abs(r24["max_drawdown"])),
        "min_return_edge_pp":min(100*(r23["total_return"]-V510C_REF["2023"]["return"]),100*(r24["total_return"]-V510C_REF["2024"]["return"])),
        "min_dd_improvement_pp":min(100*(abs(V510C_REF["2023"]["dd"])-abs(r23["max_drawdown"])),100*(abs(V510C_REF["2024"]["dd"])-abs(r24["max_drawdown"]))),
    }
def final_score(rf):
    strict=(rf["total_return"]>V32_FINAL_REF["return"]+EPS and abs(rf["max_drawdown"])<abs(V32_FINAL_REF["dd"])-EPS and rf["weekly"]["active_ge_2_rate"]>=V32_FINAL_REF["active_ge2"]-EPS)
    return {"strict_final_better_than_v32":strict,"return_edge_pp":100*(rf["total_return"]-V32_FINAL_REF["return"]),"dd_improvement_pp":100*(abs(V32_FINAL_REF["dd"])-abs(rf["max_drawdown"])),"active_ge2_edge_pp":100*(rf["weekly"]["active_ge_2_rate"]-V32_FINAL_REF["active_ge2"])}

def run_family(version,name,family,configs,outfile):
    data=load_data(); trades,th=build_context(data); a23=[t for t in trades if inper(t,V23)]; a24=[t for t in trades if inper(t,V24)]; af=[t for t in trades if inper(t,FINAL)]
    baseline={"2023":slim(v58.simulate(a23,data,V23,None)),"2024":slim(v58.simulate(a24,data,V24,None)),"final_research_period":slim(v58.simulate(af,data,FINAL,None))}
    rows=[]; eligible=[]
    for cfg in configs:
        r23=simulate(a23,data,V23,th,family,cfg); r24=simulate(a24,data,V24,th,family,cfg); sc=validation_score(r23,r24)
        z={"config":cfg,"2023":slim(r23),"2024":slim(r24),**sc}; rows.append(z)
        if sc["strict_validation_better_than_v510c"]: eligible.append(z)
    key=lambda z:(z["strict_validation_better_than_v510c"],z["min_dd_improvement_pp"],z["min_return_edge_pp"],z["return_edge_2024_pp"]+z["return_edge_2023_pp"])
    rows.sort(key=key,reverse=True); eligible.sort(key=key,reverse=True); best=eligible[0] if eligible else rows[0]
    rf=None; fsc=None
    if eligible:
        rf=simulate(af,data,FINAL,th,family,best["config"]); fsc=final_score(rf)
    status="Strict final pass" if (fsc and fsc["strict_final_better_than_v32"]) else ("Validation pass / final fail" if eligible else "Rejected / no strict validation dominance")
    result={"version":version,"name":name,"family":family,"status":status,"thresholds":th,
            "strict_definition":"Candidate must have higher return AND lower absolute max drawdown than v5.10C in both 2023 and 2024, while preserving active-week >=2% rate. Only the top validation-passing configuration may open final. Final must then beat v3.2 on return and drawdown while preserving active-week >=2% rate.",
            "v510c_validation_reference":V510C_REF,"v32_final_reference":V32_FINAL_REF,
            "dataset":{"stocks":len(data),"signals":len(trades)},"hazard_profiles":{"2023":profile(a23,th),"2024":profile(a24,th),"final_research_period":profile(af,th)},
            "baseline_v32":baseline,"grid":{"tested":len(rows),"strict_validation_pass":len(eligible)},"best":best,"final_result":slim(rf) if rf else None,"final_score":fsc,"top20":rows[:20],
            "notes":["v5.9C hazard detector is frozen from 2021-2022 quantiles.","All post-entry decisions use only information available by that session close; intraday stop/target is evaluated first, stop-first on same-bar ambiguity.","0.5% round-trip friction sensitivity is retained.","Final research period is not used to choose configurations."]}
    with open(outfile,"w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({"version":version,"status":status,"grid":result["grid"],"best":best,"final_result":result["final_result"],"final_score":fsc},ensure_ascii=False,indent=2))
    return result
