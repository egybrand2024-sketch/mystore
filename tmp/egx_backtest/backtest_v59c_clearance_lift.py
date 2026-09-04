import glob,json,os,sys
sys.path.insert(0,"tmp/egx_backtest")
import analyze_v58_hazard_attribution as hz
import backtest_v58_selective_hazard_gate as v58

TRAIN=("2021-01-01","2022-12-31"); V23=("2023-01-01","2023-12-31"); V24=("2024-01-01","2024-12-31"); FINAL=("2025-01-01","2026-02-28")
PROBES=[0.30,0.35,0.40,0.45]
CONFIRMS=["mfe_ge_2pct","close_ge_entry","close_ge_entry_and_mfe_ge_2pct"]
ACTIONS=["hold_probe","exit_probe"]
MIN_WEALTH=0.98; MIN_DD_RED=0.10; MIN_ACTIVE=0.95; MAX_HAZARD=0.35
NAME="Defensive Lift v5.9C — Clearance + High Lift"

def inper(t,p): return p[0]<=t["entry_date"]<=p[1] and t["exit_date"]<=p[1]
def slim(x): return {k:v for k,v in x.items() if k not in {"realized","curve"}}
def q(vals,p): return hz.quantile([x for x in vals if hz.finite(x)],p)
def profile(arr,rule):
    f=[t for t in arr if rule(t)]
    return {"n":len(f),"share":len(f)/len(arr) if arr else 0,"targets":sum(t["exit_type"]=="target" for t in f),"stops":sum(t["exit_type"]=="stop" for t in f),"fast_stops":sum(t["exit_type"]=="stop" and t["holding"]<=2 for t in f),"target_rate":sum(t["exit_type"]=="target" for t in f)/len(f) if f else 0,"fast_stop_rate":sum(t["exit_type"]=="stop" and t["holding"]<=2 for t in f)/len(f) if f else 0}
def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw"); data={}
    for fp in sorted(glob.glob(os.path.join(root,"*","*.csv"))):
        s=os.path.basename(fp).split(".")[0].upper(); rows=hz.v3.load_csv_all(fp)
        if len(rows)>=100:data[s]=rows
    trades=hz.build(data); tr=[t for t in trades if TRAIN[0]<=t["entry_date"]<=TRAIN[1]]
    c_thr=q([t["clearance"] for t in tr],0.75); l_thr=q([t["lift"] for t in tr],0.75)
    def rule(t): return t.get("clearance") is not None and t.get("lift") is not None and t["clearance"]>=c_thr and t["lift"]>=l_thr
    v58.is_hazard=lambda t,mode: rule(t)
    a23=[t for t in trades if inper(t,V23)]; a24=[t for t in trades if inper(t,V24)]; af=[t for t in trades if inper(t,FINAL)]
    b23=v58.simulate(a23,data,V23,None); b24=v58.simulate(a24,data,V24,None); bf=v58.simulate(af,data,FINAL,None)
    p23=profile(a23,rule); p24=profile(a24,rule); pf=profile(af,rule)
    rows=[]; eligible=[]
    for probe in PROBES:
      for conf in CONFIRMS:
       for act in ACTIONS:
        cfg={"hazard_mode":"v59c","probe_frac":probe,"confirm_mode":conf,"unconfirmed_action":act}
        r23=v58.simulate(a23,data,V23,cfg); r24=v58.simulate(a24,data,V24,cfg)
        wr23=(1+r23["total_return"])/(1+b23["total_return"]); wr24=(1+r24["total_return"])/(1+b24["total_return"])
        dr23=1-abs(r23["max_drawdown"])/abs(b23["max_drawdown"]); dr24=1-abs(r24["max_drawdown"])/abs(b24["max_drawdown"])
        ar23=r23["weekly"]["active_ge_2_rate"]/b23["weekly"]["active_ge_2_rate"] if b23["weekly"]["active_ge_2_rate"] else 1
        ar24=r24["weekly"]["active_ge_2_rate"]/b24["weekly"]["active_ge_2_rate"] if b24["weekly"]["active_ge_2_rate"] else 1
        z={"config":cfg,"2023":slim(r23),"2024":slim(r24),"min_wealth_ratio":min(wr23,wr24),"min_dd_reduction":min(dr23,dr24),"min_active_ge2_ratio":min(ar23,ar24),"hazard_share_max":max(p23["share"],p24["share"])}
        z["strict_eligible"]=z["min_wealth_ratio"]>=MIN_WEALTH and z["min_dd_reduction"]>=MIN_DD_RED and z["min_active_ge2_ratio"]>=MIN_ACTIVE and z["hazard_share_max"]<=MAX_HAZARD
        rows.append(z)
        if z["strict_eligible"]: eligible.append(z)
    key=lambda z:(z["strict_eligible"],z["min_dd_reduction"],z["min_wealth_ratio"],z["min_active_ge2_ratio"])
    rows.sort(key=key,reverse=True); eligible.sort(key=key,reverse=True)
    best=eligible[0] if eligible else rows[0]
    final=v58.simulate(af,data,FINAL,best["config"]) if best["strict_eligible"] else None
    result={"version":"v5.9C","name":NAME,"status":"Eligible" if best["strict_eligible"] else "Rejected / Near Miss","hazard_rule":{"clearance_gte_train_q75":c_thr,"lift_gte_train_q75":l_thr},"profiles":{"2023":p23,"2024":p24,"final_research_period":pf},"baseline":{"2023":slim(b23),"2024":slim(b24),"final_research_period":slim(bf)},"grid":{"tested":len(rows),"strict_eligible":len(eligible),"probes":PROBES,"confirms":CONFIRMS,"actions":ACTIONS},"criteria":{"min_wealth_ratio_each_validation":MIN_WEALTH,"min_dd_reduction_each_validation":MIN_DD_RED,"min_active_ge2_ratio_each_validation":MIN_ACTIVE,"max_hazard_share":MAX_HAZARD},"best":best,"final_result":slim(final) if final else None,"top10":rows[:10],"notes":["Thresholds frozen from 2021-2022 raw DLP signals.","2023/2024 only used for validation and configuration selection.","Final research period is only opened if a strict eligible configuration exists.","Normal non-hazard DLP entries remain exact 50% v3.2 entries."]}
    if final: result["final_comparison"]={"wealth_ratio":(1+final["total_return"])/(1+bf["total_return"]),"dd_reduction":1-abs(final["max_drawdown"])/abs(bf["max_drawdown"]),"return_change_pp":100*(final["total_return"]-bf["total_return"])}
    with open("tmp/egx_backtest/results_v59c_clearance_lift.json","w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ["version","status","hazard_rule","profiles","grid","best","final_result"]},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
