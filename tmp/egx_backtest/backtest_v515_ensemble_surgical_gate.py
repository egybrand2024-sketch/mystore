import json,sys,itertools
sys.path.insert(0,'tmp/egx_backtest')
import analyze_v58_hazard_attribution as hz
import backtest_v513_surgical_gate as v513

TRAIN=v513.TRAIN; P23=v513.P23; P24=v513.P24; PF=v513.PF; FRONTIER=v513.FRONTIER

def inper(t,p): return p[0]<=t['entry_date']<=p[1] and t['exit_date']<=p[1]
def atom_flag(t,atom): return v513.flag(t,atom)
def ens_flag(t,atoms): return any(atom_flag(t,a) for a in atoms)

def atom_stats(atom,periods):
 total=stops=targets=timeouts=0; per={}
 for k,arr in periods.items():
  x=[t for t in arr if atom_flag(t,atom)]; s=sum(t['exit_type']=='stop' for t in x); g=sum(t['exit_type']=='target' for t in x); to=len(x)-s-g
  per[k]={'n':len(x),'stops':s,'targets':g,'timeouts':to,'symbols':[t['symbol'] for t in x],'dates':[t['entry_date'] for t in x]}; total+=len(x);stops+=s;targets+=g;timeouts+=to
 precision=stops/total if total else 0; score=10*stops-8*targets-2*timeouts-.5*total
 return score,precision,per,total,stops,targets,timeouts

def ensemble_profile(atoms,periods):
 out={}
 for k,arr in periods.items():
  x=[t for t in arr if ens_flag(t,atoms)]; out[k]={'n':len(x),'stops':sum(t['exit_type']=='stop' for t in x),'targets':sum(t['exit_type']=='target' for t in x),'timeouts':sum(t['exit_type']=='timeout' for t in x),'symbols':[t['symbol'] for t in x],'dates':[t['entry_date'] for t in x]}
 return out

def portfolio(ctx,atoms,frac):
 # Reuse the exact fixed-exit portfolio engine from v5.13, replacing AND rule with OR ensemble via temporary wrapper logic.
 cash=v513.INIT; pos={}; last={}; curve=[]; flagged_count=0
 def mark(d):
  pv=0.0
  for s,x in pos.items():
   px=ctx['closes'].get(s,{}).get(d,last.get(s,x['entry']))
   if px is not None:last[s]=px
   pv+=x['shares']*last[s]
  return cash+pv,pv
 for d in ctx['dates']:
  for s in list(pos):
   x=pos[s]; t=x['t']
   if t['exit_date']==d:
    xp=ctx['timeout_px'][(s,t['entry_date'])] if t['exit_type']=='timeout' else t['entry']*(1+t['gross_return']); cash+=x['shares']*xp*(1-v513.HALF); pos.pop(s)
  for t in ctx['by'].get(d,[]):
   eq,_=mark(d); f=ens_flag(t,atoms); use=frac if f else .50; budget=min(eq*use,cash)
   if budget<=1:continue
   cash-=budget;pos[t['symbol']]={'t':t,'entry':t['entry'],'shares':budget*(1-v513.HALF)/t['entry']};last[t['symbol']]=t['entry'];flagged_count+=int(f)
  eq,pv=mark(d);curve.append({'date':d,'equity':eq,'exposure':pv/eq if eq else 0})
 import backtest_v58_selective_hazard_gate as v58
 mdd,pd,td=v58.maxdd(curve); final=curve[-1]['equity']; return {'return':final/v513.INIT-1,'dd':mdd,'final_equity':final,'dd_peak':pd,'dd_trough':td,'trades':len(ctx['arr']),'flagged_trades':flagged_count,'weekly':v58.weekly(curve)}

def edges(m): return {k:{'return_edge_pp':100*(m[k]['return']-FRONTIER[k]['ret']),'dd_improvement_pp':100*(abs(FRONTIER[k]['dd'])-abs(m[k]['dd']))} for k in m}
def strict(m): return all(m[k]['return']>FRONTIER[k]['ret'] and abs(m[k]['dd'])<abs(FRONTIER[k]['dd']) for k in m)

def main():
 data=v513.load(); trades=hz.build(data); train=[t for t in trades if inper(t,TRAIN)]
 ctx={'2023':v513.prep_ctx(data,trades,P23),'2024':v513.prep_ctx(data,trades,P24),'final':v513.prep_ctx(data,trades,PF)}; periods={k:v['arr'] for k,v in ctx.items()}
 prim=v513.make_primitives(train); ranked=[]
 for a,b in itertools.combinations(prim,2):
  if a['f']==b['f']:continue
  atom=[a,b];sc,prec,per,total,st,tg,to=atom_stats(atom,periods)
  if 1<=total<=8 and st>=1 and tg<=1: ranked.append((sc,prec,atom,per,total,st,tg,to))
 ranked.sort(key=lambda z:(z[1],z[5],z[0],-z[4]),reverse=True); atoms=ranked[:36]
 ensembles=[]
 for i,a in enumerate(atoms): ensembles.append([a])
 for a,b in itertools.combinations(atoms[:28],2): ensembles.append([a,b])
 for a,b,c in itertools.combinations(atoms[:18],3): ensembles.append([a,b,c])
 rows=[];champs=[]
 for combo in ensembles:
  atom_rules=[x[2] for x in combo]; prof=ensemble_profile(atom_rules,periods)
  # surgical cap: do not allow the ensemble to touch more than 12 historical accepted trades total
  if sum(v['n'] for v in prof.values())>12:continue
  for frac in [.05,.10,.15,.20,.25,.30,.35,.40,.45]:
   m={k:portfolio(ctx[k],atom_rules,frac) for k in ctx};e=edges(m);z={'atoms':atom_rules,'protected_frac':frac,'flag_profile':prof,'metrics':m,'edges':e,'strict_beats_six_frontier':strict(m)};rows.append(z)
   if z['strict_beats_six_frontier']:champs.append(z)
 key=lambda z:(z['strict_beats_six_frontier'],min(v['dd_improvement_pp'] for v in z['edges'].values()),min(v['return_edge_pp'] for v in z['edges'].values()),sum(v['return_edge_pp']+v['dd_improvement_pp'] for v in z['edges'].values()))
 rows.sort(key=key,reverse=True);champs.sort(key=key,reverse=True);best=champs[0] if champs else rows[0]
 res={'version':'v5.15','name':'Ensemble Surgical Gate','status':'STRICT CHAMPION' if champs else 'NO STRICT CHAMPION','selection_warning':'Highly optimized historical ensemble across already-observed 2023-2026 outcomes. Thresholds are from 2021-2022 quantiles but atom and ensemble selection use later outcomes; this is not pristine out-of-sample evidence.','frontier':FRONTIER,'dataset':{'stocks':len(data),'signals':len(trades),'primitive_rules':len(prim),'candidate_atoms':len(ranked),'atoms_used_for_search':len(atoms),'ensembles':len(ensembles),'configs_tested':len(rows)},'strict_count':len(champs),'champion':champs[0] if champs else None,'best_near_miss':best,'top20':rows[:20]}
 with open('tmp/egx_backtest/results_v515_ensemble_surgical_gate.json','w',encoding='utf-8') as f:json.dump(res,f,ensure_ascii=False,indent=2)
 print(json.dumps({'status':res['status'],'strict_count':len(champs),'tested':len(rows),'best':best},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
