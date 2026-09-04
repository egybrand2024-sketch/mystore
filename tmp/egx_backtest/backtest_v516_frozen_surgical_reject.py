import json,sys
sys.path.insert(0,'tmp/egx_backtest')
import analyze_v58_hazard_attribution as hz
import backtest_v513_surgical_gate as v513
import backtest_v515_ensemble_surgical_gate as v515

P23=v513.P23;P24=v513.P24;PF=v513.PF;FRONTIER=v513.FRONTIER
ATOMS=[
 [
  {'f':'rs20','side':'high','thr':0.07340059829329726,'q':0.75},
  {'f':'market5_ret','side':'high','thr':0.008543451793102896,'q':0.70},
 ],
 [
  {'f':'lift','side':'high','thr':0.05965902346208485,'q':0.75},
  {'f':'gap','side':'low','thr':-3.413044438183023e-08,'q':0.15},
 ]
]

def edges(m):return {k:{'return_edge_pp':100*(m[k]['return']-FRONTIER[k]['ret']),'dd_improvement_pp':100*(abs(FRONTIER[k]['dd'])-abs(m[k]['dd']))} for k in m}
def strict(m):return all(m[k]['return']>FRONTIER[k]['ret'] and abs(m[k]['dd'])<abs(FRONTIER[k]['dd']) for k in m)
def main():
 data=v513.load();trades=hz.build(data);ctx={'2023':v513.prep_ctx(data,trades,P23),'2024':v513.prep_ctx(data,trades,P24),'final':v513.prep_ctx(data,trades,PF)};periods={k:v['arr'] for k,v in ctx.items()}
 profile=v515.ensemble_profile(ATOMS,periods);rows=[]
 for frac in [0.0,0.01,0.025,0.05,0.075,0.10,0.15]:
  m={k:v515.portfolio(ctx[k],ATOMS,frac) for k in ctx};e=edges(m);rows.append({'protected_frac':frac,'metrics':m,'edges':e,'strict_beats_six_frontier':strict(m)})
 rows.sort(key=lambda z:(z['strict_beats_six_frontier'],min(v['dd_improvement_pp'] for v in z['edges'].values()),min(v['return_edge_pp'] for v in z['edges'].values())),reverse=True);champ=[z for z in rows if z['strict_beats_six_frontier']]
 res={'version':'v5.16','name':'Frozen Surgical Reject Sensitivity','status':'STRICT CHAMPION' if champ else 'NO STRICT CHAMPION','selection_warning':'The two-atom ensemble was selected after inspecting already-observed 2023-2026 outcomes in v5.15. v5.16 only freezes that rule and tests allocation sensitivity; it is historical optimization, not pristine out-of-sample evidence.','atoms':ATOMS,'flag_profile':profile,'frontier':FRONTIER,'configs_tested':len(rows),'strict_count':len(champ),'champion':champ[0] if champ else None,'all_results':rows}
 with open('tmp/egx_backtest/results_v516_frozen_surgical_reject.json','w',encoding='utf-8') as f:json.dump(res,f,ensure_ascii=False,indent=2)
 print(json.dumps(res,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
