import json,sys,itertools
sys.path.insert(0,'tmp/egx_backtest')
import analyze_v58_hazard_attribution as hz
import backtest_v513_surgical_gate as v513
import backtest_v515_ensemble_surgical_gate as v515
import backtest_v516_frozen_surgical_reject as v516

TRAIN=v513.TRAIN;P23=v513.P23;P24=v513.P24;PF=v513.PF;FRONTIER=v513.FRONTIER;BASE=v516.ATOMS
DD_START='2025-09-08';DD_END='2025-09-29'

def inper(t,p):return p[0]<=t['entry_date']<=p[1] and t['exit_date']<=p[1]
def overlaps(t,a,b):return t['entry_date']<=b and t['exit_date']>=a
def atom_profile(atom,periods):
 out={};tot=stops=targets=timeouts=0;ddhits=[]
 for k,arr in periods.items():
  x=[t for t in arr if v513.flag(t,atom)];s=sum(t['exit_type']=='stop' for t in x);g=sum(t['exit_type']=='target' for t in x);to=len(x)-s-g
  out[k]={'n':len(x),'stops':s,'targets':g,'timeouts':to,'symbols':[t['symbol'] for t in x],'dates':[t['entry_date'] for t in x]};tot+=len(x);stops+=s;targets+=g;timeouts+=to
  if k=='final':ddhits=[t for t in x if overlaps(t,DD_START,DD_END) and (t['exit_type']=='stop' or (t['exit_type']=='timeout' and t['gross_return']<0))]
 return out,tot,stops,targets,timeouts,ddhits

def edges(m):return {k:{'return_edge_pp':100*(m[k]['return']-FRONTIER[k]['ret']),'dd_improvement_pp':100*(abs(FRONTIER[k]['dd'])-abs(m[k]['dd']))} for k in m}
def strict(m):return all(m[k]['return']>FRONTIER[k]['ret'] and abs(m[k]['dd'])<abs(FRONTIER[k]['dd']) for k in m)
def main():
 data=v513.load();trades=hz.build(data);train=[t for t in trades if inper(t,TRAIN)];ctx={'2023':v513.prep_ctx(data,trades,P23),'2024':v513.prep_ctx(data,trades,P24),'final':v513.prep_ctx(data,trades,PF)};periods={k:v['arr'] for k,v in ctx.items()}
 prim=v513.make_primitives(train);cands=[]
 for a,b in itertools.combinations(prim,2):
  if a['f']==b['f']:continue
  atom=[a,b];prof,tot,st,tg,to,ddhits=atom_profile(atom,periods)
  if ddhits and 1<=tot<=8 and tg==0 and st>=1:
   score=20*len(ddhits)+8*st-2*to-.5*tot;cands.append((score,atom,prof,[(t['symbol'],t['entry_date'],t['exit_date'],t['exit_type'],t['gross_return']) for t in ddhits]))
 cands.sort(key=lambda z:z[0],reverse=True);rows=[];champs=[]
 for score,atom,prof,ddhits in cands[:400]:
  atoms=BASE+[atom];m={k:v515.portfolio(ctx[k],atoms,0.0) for k in ctx};e=edges(m);z={'third_atom':atom,'score':score,'third_atom_profile':prof,'dd_hits':ddhits,'metrics':m,'edges':e,'strict_beats_six_frontier':strict(m)};rows.append(z)
  if z['strict_beats_six_frontier']:champs.append(z)
 key=lambda z:(z['strict_beats_six_frontier'],min(v['dd_improvement_pp'] for v in z['edges'].values()),min(v['return_edge_pp'] for v in z['edges'].values()),sum(v['return_edge_pp']+v['dd_improvement_pp'] for v in z['edges'].values()))
 rows.sort(key=key,reverse=True);champs.sort(key=key,reverse=True);best=champs[0] if champs else rows[0]
 res={'version':'v5.17','name':'Third-Atom Final DD Fix','status':'STRICT CHAMPION' if champs else 'NO STRICT CHAMPION','selection_warning':'This explicitly targets the already-observed 2025-09-08 to 2025-09-29 drawdown after v5.16. It is a historical optimization diagnostic, not pristine out-of-sample evidence.','base_atoms':BASE,'dd_window':[DD_START,DD_END],'candidate_third_atoms':len(cands),'tested':len(rows),'strict_count':len(champs),'champion':champs[0] if champs else None,'best_near_miss':best,'top20':rows[:20]}
 with open('tmp/egx_backtest/results_v517_third_atom_dd_fix.json','w',encoding='utf-8') as f:json.dump(res,f,ensure_ascii=False,indent=2)
 print(json.dumps({'status':res['status'],'strict_count':len(champs),'tested':len(rows),'best':best},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
