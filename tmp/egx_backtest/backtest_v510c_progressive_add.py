import glob,json,os,sys
sys.path.insert(0,"tmp/egx_backtest")
import analyze_v58_hazard_attribution as hz
import backtest_v58_selective_hazard_gate as v58
import backtest_v510a_soft_momentum_hold as a
from collections import defaultdict
from datetime import datetime

TRAIN=("2021-01-01","2022-12-31"); V23=("2023-01-01","2023-12-31"); V24=("2024-01-01","2024-12-31"); FINAL=("2025-01-01","2026-02-28")
START_FRACS=[0.35,0.375,0.40]
MID_FRACS=[0.425,0.45,0.475]
D1_MFE=[0.01,0.015,0.02]
D2_CLOSE=[0.0,0.005]
MIN_WEALTH=1.00; MIN_DD_RED=0.10; MIN_ACTIVE=0.95
NAME="Defensive Lift v5.10C — Progressive 2-Step Add"

def inper(t,p): return p[0]<=t["entry_date"]<=p[1] and t["exit_date"]<=p[1]
def slim(x): return {k:v for k,v in x.items() if k not in {"curve","realized"}}
def q(vals,p): return hz.quantile([x for x in vals if hz.finite(x)],p)

def simulate(trades,data,period,rule,cfg=None):
    dates=sorted({r["date"] for rows in data.values() for r in rows if period[0]<=r["date"]<=period[1]})
    closes={s:{r["date"]:r["close"] for r in rows} for s,rows in data.items()}; highs={s:{r["date"]:r["high"] for r in rows} for s,rows in data.items()}
    eb=defaultdict(list)
    for t in trades: eb[t["entry_date"]].append(t)
    for d in eb: eb[d].sort(key=lambda x:(-x["liquidity"],x["symbol"]))
    cash=100000.0; pos={}; last={}; curve=[]; real=[]; skipped=0; adds1=adds2=hzentries=0
    def mark(d):
        pv=0
        for s,p in pos.items():
            px=closes.get(s,{}).get(d,last.get(s,p["entry"]))
            if px is not None:last[s]=px
            pv+=p["shares"]*last[s]
        return cash+pv,pv
    for d in dates:
        for s in list(pos):
            p=pos[s]; px=closes[s].get(d)
            if px is None: continue
            last[s]=px
            if d==p["entry_date"]: continue
            p["age"]+=1
            if d==p["exit_date"]:
                proceeds=p["shares"]*p["exit_price"]*(1-a.HALF_FRICTION); cash+=proceeds
                real.append({"symbol":s,"exit_type":p["exit_type"],"hazard":p["hazard"],"cash_return":proceeds/p["budget"]-1,"stage":p["stage"]}); pos.pop(s); continue
            if cfg and p["hazard"] and p["age"]==1 and p["stage"]==0:
                if highs[s][d]/p["entry"]-1>=cfg["d1_mfe"]:
                    target=p["equity_at_entry"]*cfg["mid_frac"]; add=min(max(0,target-p["budget"]),cash)
                    if add>1:
                        p["shares"]+=add*(1-a.HALF_FRICTION)/px; p["budget"]+=add; cash-=add; p["stage"]=1; adds1+=1
            if cfg and p["hazard"] and p["age"]==2 and p["stage"]>=1 and p["stage"]<2:
                if px/p["entry"]-1>=cfg["d2_close"]:
                    target=p["equity_at_entry"]*.50; add=min(max(0,target-p["budget"]),cash)
                    if add>1:
                        p["shares"]+=add*(1-a.HALF_FRICTION)/px; p["budget"]+=add; cash-=add; p["stage"]=2; adds2+=1
        for t in eb.get(d,[]):
            s=t["symbol"]
            if s in pos or len(pos)>=2: skipped+=1; continue
            eq,_=mark(d); hzd=bool(cfg and rule(t)); frac=cfg["start_frac"] if hzd else .50
            budget=min(eq*frac,cash)
            if budget<=1: skipped+=1; continue
            shares=budget*(1-a.HALF_FRICTION)/t["entry"]; cash-=budget
            pos[s]={"shares":shares,"budget":budget,"equity_at_entry":eq,"entry":t["entry"],"entry_date":d,"exit_date":t["exit_date"],"exit_type":t["exit_type"],"exit_price":a.exit_price(t,data),"age":0,"hazard":hzd,"stage":0 if hzd else 2}
            if hzd: hzentries+=1
            last[s]=t["entry"]
        eq,pv=mark(d); curve.append({"date":d,"equity":eq,"exposure":pv/eq if eq else 0})
    mdd,pd,td=v58.maxdd(curve); final=curve[-1]["equity"]; d0=datetime.fromisoformat(curve[0]["date"]).date(); d1=datetime.fromisoformat(curve[-1]["date"]).date(); yrs=max((d1-d0).days/365.25,1/365.25)
    return {"trades":len(real),"skipped":skipped,"final_equity":final,"total_return":final/100000-1,"cagr":(final/100000)**(1/yrs)-1,"max_drawdown":mdd,"dd_peak":pd,"dd_trough":td,"weekly":v58.weekly(curve),"avg_exposure":v58.mean([x["exposure"] for x in curve]),"hazard_runtime":{"entries":hzentries,"day1_adds":adds1,"day2_adds":adds2},"realized":real,"curve":curve}

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw"); data={}
    for fp in sorted(glob.glob(os.path.join(root,"*","*.csv"))):
        s=os.path.basename(fp).split(".")[0].upper(); rows=hz.v3.load_csv_all(fp)
        if len(rows)>=100:data[s]=rows
    trades=hz.build(data); tr=[t for t in trades if TRAIN[0]<=t["entry_date"]<=TRAIN[1]]
    cthr=q([t["clearance"] for t in tr],.75); lthr=q([t["lift"] for t in tr],.75)
    rule=lambda t: hz.finite(t.get("clearance")) and hz.finite(t.get("lift")) and t["clearance"]>=cthr and t["lift"]>=lthr
    a23=[t for t in trades if inper(t,V23)]; a24=[t for t in trades if inper(t,V24)]; af=[t for t in trades if inper(t,FINAL)]
    b23=v58.simulate(a23,data,V23,None); b24=v58.simulate(a24,data,V24,None); bf=v58.simulate(af,data,FINAL,None)
    rows=[]; eligible=[]
    for sf in START_FRACS:
      for mf in MID_FRACS:
       if mf<=sf: continue
       for m1 in D1_MFE:
        for c2 in D2_CLOSE:
          cfg={"start_frac":sf,"mid_frac":mf,"d1_mfe":m1,"d2_close":c2}
          r23=simulate(a23,data,V23,rule,cfg); r24=simulate(a24,data,V24,rule,cfg)
          wr1=(1+r23["total_return"])/(1+b23["total_return"]); wr2=(1+r24["total_return"])/(1+b24["total_return"])
          dr1=1-abs(r23["max_drawdown"])/abs(b23["max_drawdown"]); dr2=1-abs(r24["max_drawdown"])/abs(b24["max_drawdown"])
          ar1=r23["weekly"]["active_ge_2_rate"]/b23["weekly"]["active_ge_2_rate"]; ar2=r24["weekly"]["active_ge_2_rate"]/b24["weekly"]["active_ge_2_rate"]
          z={"config":cfg,"2023":slim(r23),"2024":slim(r24),"min_wealth_ratio":min(wr1,wr2),"min_dd_reduction":min(dr1,dr2),"min_active_ge2_ratio":min(ar1,ar2)}
          z["strict_eligible"]=z["min_wealth_ratio"]>=MIN_WEALTH and z["min_dd_reduction"]>=MIN_DD_RED and z["min_active_ge2_ratio"]>=MIN_ACTIVE
          rows.append(z); eligible.append(z) if z["strict_eligible"] else None
    key=lambda z:(z["strict_eligible"],z["min_dd_reduction"],z["min_wealth_ratio"]); rows.sort(key=key,reverse=True); eligible.sort(key=key,reverse=True)
    best=eligible[0] if eligible else rows[0]; rf=simulate(af,data,FINAL,rule,best["config"]) if best["strict_eligible"] else None
    result={"version":"v5.10C","name":NAME,"status":"Eligible" if best["strict_eligible"] else "Rejected / Near Miss","hazard_rule":{"clearance_gte":cthr,"lift_gte":lthr},"architecture":"Hazard trade enters smaller, adds partially after day-1 MFE confirmation, then reaches 50% only if day-2 close remains constructive. No early exit or reduction.","baseline":{"2023":slim(b23),"2024":slim(b24),"final_research_period":slim(bf)},"grid":{"tested":len(rows),"eligible":len(eligible)},"best":best,"final_result":slim(rf) if rf else None,"top10":rows[:10]}
    if rf: result["final_comparison"]={"wealth_ratio":(1+rf["total_return"])/(1+bf["total_return"]),"dd_reduction":1-abs(rf["max_drawdown"])/abs(bf["max_drawdown"]),"pareto_better_than_v32":rf["total_return"]>=bf["total_return"] and abs(rf["max_drawdown"])<=abs(bf["max_drawdown"])}
    with open("tmp/egx_backtest/results_v510c_progressive_add.json","w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ["version","status","grid","best","final_result"]},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
