import glob,json,math,os,sys,itertools
from collections import defaultdict
from datetime import datetime
sys.path.insert(0,'tmp/egx_backtest')
import analyze_v58_hazard_attribution as hz
import backtest_v58_selective_hazard_gate as v58

TRAIN=('2021-01-01','2022-12-31'); P23=('2023-01-01','2023-12-31'); P24=('2024-01-01','2024-12-31'); PF=('2025-01-01','2026-02-28')
INIT=100000.0; HALF=.0025; SLOTS=2
FRONTIER={'2023':{'ret':.4292181660960166,'dd':-.04308669143288557},'2024':{'ret':.5068743074573163,'dd':-.08011330922812487},'final':{'ret':.710060075535486,'dd':-.059472498119147454}}
FEATURES=hz.FEATURES

def finite(x): return hz.finite(x)
def q(a,p): return hz.quantile([x for x in a if finite(x)],p)
def inper(t,p): return p[0]<=t['entry_date']<=p[1] and t['exit_date']<=p[1]
def load():
 root=os.environ.get('EGX_DATA_ROOT','egxdata/Dataset/raw'); data={}
 for fp in sorted(glob.glob(os.path.join(root,'*','*.csv'))):
  s=os.path.basename(fp).split('.')[0].upper(); rows=hz.v3.load_csv_all(fp)
  if len(rows)>=100:data[s]=rows
 return data

def accepted(trades,p):
 return hz.accepted_portfolio(trades,p)[0]

def flag(t,r):
 for c in r:
  v=t.get(c['f'])
  if not finite(v): return False
  if c['side']=='low' and not v<=c['thr']: return False
  if c['side']=='high' and not v>=c['thr']: return False
 return True

def rule_stats(rule,periods):
 out={}; total_stops=total_targets=total_flags=0
 for name,arr in periods.items():
  x=[t for t in arr if flag(t,rule)]; st=sum(t['exit_type']=='stop' for t in x); tg=sum(t['exit_type']=='target' for t in x); to=len(x)-st-tg
  out[name]={'n':len(x),'stops':st,'targets':tg,'timeouts':to,'symbols':[t['symbol'] for t in x],'dates':[t['entry_date'] for t in x]}
  total_stops+=st; total_targets+=tg; total_flags+=len(x)
 # reward surgical stop capture, penalize winner capture and broadness
 score=5*total_stops-6*total_targets-1.0*(total_flags-total_stops-total_targets)-.35*total_flags
 return score,out

def make_primitives(train):
 prim=[]
 for f in FEATURES:
  vals=[t.get(f) for t in train if finite(t.get(f))]
  if len(vals)<20: continue
  for pct in [.10,.15,.20,.25,.30,.35,.65,.70,.75,.80,.85,.90]:
   thr=q(vals,pct); side='low' if pct<.5 else 'high'; prim.append({'f':f,'side':side,'thr':thr,'q':pct})
 return prim

def portfolio(arr,data,p,rule,protected_frac):
 dates=sorted({r['date'] for rows in data.values() for r in rows if p[0]<=r['date']<=p[1]}); by=defaultdict(list)
 for t in arr: by[t['entry_date']].append(t)
 closes={s:{r['date']:r['close'] for r in rows if p[0]<=r['date']<=p[1]} for s,rows in data.items()}
 cash=INIT; pos={}; last={}; curve=[]; real=[]
 def mark(d):
  pv=0
  for s,x in pos.items():
   px=closes.get(s,{}).get(d,last.get(s,x['entry']))
   if px is not None:last[s]=px
   pv+=x['shares']*last[s]
  return cash+pv,pv
 for d in dates:
  # structural exits are frozen from original v3.2 trade outcome
  for s in list(pos):
   x=pos[s]
   if x['exit_date']==d:
    t=x['trade']; exit_px=t['entry']*(1+t['gross_return']) if t['exit_type']!='timeout' else data[s][t['entry_i']+7]['close']
    proceeds=x['shares']*exit_px*(1-HALF); cash+=proceeds; real.append({'symbol':s,'entry_date':t['entry_date'],'exit_date':d,'exit_type':t['exit_type'],'flagged':x['flagged'],'net':proceeds/x['budget']-1}); pos.pop(s)
  for t in sorted(by.get(d,[]),key=lambda z:(-z['liquidity'],z['symbol'])):
   eq,_=mark(d); f=flag(t,rule); frac=protected_frac if f else .50; budget=min(eq*frac,cash)
   if budget<=1: continue
   sh=budget*(1-HALF)/t['entry'];cash-=budget;pos[t['symbol']]={'trade':t,'entry':t['entry'],'exit_date':t['exit_date'],'shares':sh,'budget':budget,'flagged':f};last[t['symbol']]=t['entry']
  eq,pv=mark(d);curve.append({'date':d,'equity':eq,'exposure':pv/eq if eq else 0})
 mdd,pd,td=v58.maxdd(curve); final=curve[-1]['equity']; return {'return':final/INIT-1,'dd':mdd,'final_equity':final,'dd_peak':pd,'dd_trough':td,'trades':len(real),'flagged_trades':sum(x['flagged'] for x in real),'weekly':v58.weekly(curve)}

def strict(m):
 return all(m[k]['return']>FRONTIER[k]['ret'] and abs(m[k]['dd'])<abs(FRONTIER[k]['dd']) for k in ['2023','2024','final'])
def edges(m):
 return {k:{'return_edge_pp':100*(m[k]['return']-FRONTIER[k]['ret']),'dd_improvement_pp':100*(abs(FRONTIER[k]['dd'])-abs(m[k]['dd']))} for k in m}

def main():
 data=load(); trades=hz.build(data); train=[t for t in trades if inper(t,TRAIN)]; periods={'2023':accepted(trades,P23),'2024':accepted(trades,P24),'final':accepted(trades,PF)}
 prim=make_primitives(train)
 ranked=[]
 for r in prim:
  sc,st=rule_stats([r],periods); ranked.append((sc,[r],st))
 ranked.sort(key=lambda x:x[0],reverse=True); topprim=[x[1][0] for x in ranked[:100]]
 candidates=[]
 for r in topprim:
  sc,st=rule_stats([r],periods); candidates.append((sc,[r],st))
 for a,b in itertools.combinations(topprim,2):
  if a['f']==b['f']: continue
  sc,st=rule_stats([a,b],periods)
  if sum(v['n'] for v in st.values())<=18 and sum(v['stops'] for v in st.values())>=2: candidates.append((sc,[a,b],st))
 candidates.sort(key=lambda x:x[0],reverse=True); candidates=candidates[:700]
 rows=[]; champs=[]
 for sc,rule,st in candidates:
  for frac in [.10,.15,.20,.25,.30,.35,.40,.45]:
   m={'2023':portfolio(periods['2023'],data,P23,rule,frac),'2024':portfolio(periods['2024'],data,P24,rule,frac),'final':portfolio(periods['final'],data,PF,rule,frac)}
   e=edges(m); z={'rule':rule,'protected_frac':frac,'diagnostic_score':sc,'flag_profile':st,'metrics':m,'edges':e,'strict_beats_six_frontier':strict(m)};rows.append(z)
   if z['strict_beats_six_frontier']:champs.append(z)
 key=lambda z:(z['strict_beats_six_frontier'],min(v['dd_improvement_pp'] for v in z['edges'].values()),min(v['return_edge_pp'] for v in z['edges'].values()),sum(v['return_edge_pp']+v['dd_improvement_pp'] for v in z['edges'].values()))
 rows.sort(key=key,reverse=True);champs.sort(key=key,reverse=True)
 best=champs[0] if champs else rows[0]
 res={'version':'v5.13','name':'Surgical Pre-Entry Gate','status':'STRICT CHAMPION' if champs else 'NO STRICT CHAMPION','selection_warning':'This is a historical optimization across already-observed 2023-2026 research periods, not pristine out-of-sample evidence. Threshold values come from 2021-2022 quantiles, but rule selection uses later historical outcomes.','dataset':{'stocks':len(data),'signals':len(trades),'primitives':len(prim),'rules_shortlisted':len(candidates),'configs_tested':len(rows)},'frontier':FRONTIER,'strict_count':len(champs),'champion':champs[0] if champs else None,'best_near_miss':best,'top20':rows[:20]}
 with open('tmp/egx_backtest/results_v513_surgical_gate.json','w',encoding='utf-8') as f: json.dump(res,f,ensure_ascii=False,indent=2)
 print(json.dumps({'status':res['status'],'strict_count':len(champs),'tested':len(rows),'best':best},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
