import glob,json,os,sys,itertools
from collections import defaultdict
sys.path.insert(0,'tmp/egx_backtest')
import analyze_v58_hazard_attribution as hz
import backtest_v58_selective_hazard_gate as v58

TRAIN=('2021-01-01','2022-12-31'); P23=('2023-01-01','2023-12-31'); P24=('2024-01-01','2024-12-31'); PF=('2025-01-01','2026-02-28')
INIT=100000.0; HALF=.0025
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

def flag(t,r):
 for c in r:
  v=t.get(c['f'])
  if not finite(v): return False
  if c['side']=='low' and v>c['thr']: return False
  if c['side']=='high' and v<c['thr']: return False
 return True

def make_primitives(train):
 out=[]
 for f in FEATURES:
  vals=[t.get(f) for t in train if finite(t.get(f))]
  if len(vals)<20: continue
  for pct in [.10,.15,.20,.25,.30,.35,.65,.70,.75,.80,.85,.90]:
   out.append({'f':f,'side':'low' if pct<.5 else 'high','thr':q(vals,pct),'q':pct})
 return out

def rstats(rule,periods):
 out={}; score=0
 for name,arr in periods.items():
  x=[t for t in arr if flag(t,rule)]; st=sum(t['exit_type']=='stop' for t in x); tg=sum(t['exit_type']=='target' for t in x); to=len(x)-st-tg
  out[name]={'n':len(x),'stops':st,'targets':tg,'timeouts':to,'symbols':[t['symbol'] for t in x],'dates':[t['entry_date'] for t in x]}
  score+=5*st-6*tg-1*to-.35*len(x)
 return score,out

def prep_ctx(data,trades,p):
 arr=hz.accepted_portfolio(trades,p)[0]
 dates=sorted({r['date'] for rows in data.values() for r in rows if p[0]<=r['date']<=p[1]})
 by=defaultdict(list); exits=defaultdict(list)
 for t in arr: by[t['entry_date']].append(t); exits[t['exit_date']].append(t)
 for d in by: by[d].sort(key=lambda z:(-z['liquidity'],z['symbol']))
 closes={s:{r['date']:r['close'] for r in rows if p[0]<=r['date']<=p[1]} for s,rows in data.items()}
 # timeout exit close indexed once
 timeout_px={}
 for t in arr:
  if t['exit_type']=='timeout': timeout_px[(t['symbol'],t['entry_date'])]=data[t['symbol']][t['entry_i']+7]['close']
 return {'arr':arr,'dates':dates,'by':by,'closes':closes,'timeout_px':timeout_px}

def portfolio(ctx,rule,frac):
 cash=INIT; pos={}; last={}; curve=[]; flagged_count=0
 def mark(d):
  pv=0
  for s,x in pos.items():
   px=ctx['closes'].get(s,{}).get(d,last.get(s,x['entry']))
   if px is not None:last[s]=px
   pv+=x['shares']*last[s]
  return cash+pv,pv
 for d in ctx['dates']:
  for s in list(pos):
   x=pos[s]; t=x['t']
   if t['exit_date']==d:
    xp=ctx['timeout_px'][(s,t['entry_date'])] if t['exit_type']=='timeout' else t['entry']*(1+t['gross_return'])
    cash+=x['shares']*xp*(1-HALF); pos.pop(s)
  for t in ctx['by'].get(d,[]):
   eq,_=mark(d); f=flag(t,rule); use=frac if f else .50; budget=min(eq*use,cash)
   if budget<=1: continue
   cash-=budget; pos[t['symbol']]={'t':t,'entry':t['entry'],'shares':budget*(1-HALF)/t['entry']}
   last[t['symbol']]=t['entry']; flagged_count+=int(f)
  eq,pv=mark(d); curve.append({'date':d,'equity':eq,'exposure':pv/eq if eq else 0})
 mdd,pd,td=v58.maxdd(curve); final=curve[-1]['equity']
 return {'return':final/INIT-1,'dd':mdd,'final_equity':final,'dd_peak':pd,'dd_trough':td,'trades':len(ctx['arr']),'flagged_trades':flagged_count,'weekly':v58.weekly(curve)}

def edges(m): return {k:{'return_edge_pp':100*(m[k]['return']-FRONTIER[k]['ret']),'dd_improvement_pp':100*(abs(FRONTIER[k]['dd'])-abs(m[k]['dd']))} for k in m}
def strict(m): return all(m[k]['return']>FRONTIER[k]['ret'] and abs(m[k]['dd'])<abs(FRONTIER[k]['dd']) for k in m)

def main():
 data=load(); trades=hz.build(data); train=[t for t in trades if inper(t,TRAIN)]
 ctx={'2023':prep_ctx(data,trades,P23),'2024':prep_ctx(data,trades,P24),'final':prep_ctx(data,trades,PF)}; periods={k:v['arr'] for k,v in ctx.items()}
 prim=make_primitives(train); singles=[]
 for r in prim:
  sc,st=rstats([r],periods); singles.append((sc,[r],st))
 singles.sort(key=lambda z:z[0],reverse=True); top=[x[1][0] for x in singles[:80]]
 rules=[]
 for r in top:
  sc,st=rstats([r],periods); rules.append((sc,[r],st))
 for a,b in itertools.combinations(top,2):
  if a['f']==b['f']: continue
  sc,st=rstats([a,b],periods); n=sum(v['n'] for v in st.values()); stops=sum(v['stops'] for v in st.values())
  if 2<=n<=15 and stops>=2: rules.append((sc,[a,b],st))
 rules.sort(key=lambda z:z[0],reverse=True); rules=rules[:400]
 rows=[]; champs=[]
 for sc,rule,st in rules:
  for frac in [.10,.15,.20,.25,.30,.35,.40,.45]:
   m={k:portfolio(ctx[k],rule,frac) for k in ctx}; e=edges(m); z={'rule':rule,'protected_frac':frac,'diagnostic_score':sc,'flag_profile':st,'metrics':m,'edges':e,'strict_beats_six_frontier':strict(m)}; rows.append(z)
   if z['strict_beats_six_frontier']: champs.append(z)
 key=lambda z:(z['strict_beats_six_frontier'],min(v['dd_improvement_pp'] for v in z['edges'].values()),min(v['return_edge_pp'] for v in z['edges'].values()),sum(v['return_edge_pp']+v['dd_improvement_pp'] for v in z['edges'].values()))
 rows.sort(key=key,reverse=True); champs.sort(key=key,reverse=True); best=champs[0] if champs else rows[0]
 res={'version':'v5.13','name':'Surgical Pre-Entry Gate','status':'STRICT CHAMPION' if champs else 'NO STRICT CHAMPION','selection_warning':'Historical optimization across already-observed 2023-2026 research periods; not pristine out-of-sample. Threshold values are fixed from 2021-2022 quantiles, but later outcomes are used to select the rule.','dataset':{'stocks':len(data),'signals':len(trades),'primitives':len(prim),'rules_shortlisted':len(rules),'configs_tested':len(rows)},'frontier':FRONTIER,'strict_count':len(champs),'champion':champs[0] if champs else None,'best_near_miss':best,'top20':rows[:20]}
 with open('tmp/egx_backtest/results_v513_surgical_gate.json','w',encoding='utf-8') as f: json.dump(res,f,ensure_ascii=False,indent=2)
 print(json.dumps({'status':res['status'],'strict_count':len(champs),'tested':len(rows),'best':best},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
