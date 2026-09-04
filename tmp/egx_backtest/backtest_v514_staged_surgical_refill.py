import glob,json,os,sys,itertools
from collections import defaultdict
sys.path.insert(0,'tmp/egx_backtest')
import analyze_v58_hazard_attribution as hz
import backtest_v58_selective_hazard_gate as v58
import backtest_v513_surgical_gate as v513

TRAIN=v513.TRAIN; P23=v513.P23; P24=v513.P24; PF=v513.PF
INIT=100000.0; HALF=.0025; FRONTIER=v513.FRONTIER

def finite(x): return hz.finite(x)
def inper(t,p): return p[0]<=t['entry_date']<=p[1] and t['exit_date']<=p[1]
def load(): return v513.load()
def flag(t,r): return v513.flag(t,r)

def prep(data,trades,p):
 arr=hz.accepted_portfolio(trades,p)[0]; dates=sorted({r['date'] for rows in data.values() for r in rows if p[0]<=r['date']<=p[1]}); by=defaultdict(list)
 for t in arr: by[t['entry_date']].append(t)
 for d in by: by[d].sort(key=lambda z:(-z['liquidity'],z['symbol']))
 closes={s:{r['date']:r['close'] for r in rows if p[0]<=r['date']<=p[1]} for s,rows in data.items()}; highs={s:{r['date']:r['high'] for r in rows if p[0]<=r['date']<=p[1]} for s,rows in data.items()}
 timeout_px={(t['symbol'],t['entry_date']):data[t['symbol']][t['entry_i']+7]['close'] for t in arr if t['exit_type']=='timeout'}
 return {'arr':arr,'dates':dates,'by':by,'closes':closes,'highs':highs,'timeout_px':timeout_px}

def simulate(ctx,rule,cfg):
 cash=INIT; pos={}; last={}; curve=[]; stats=defaultdict(int)
 def mark(d):
  pv=0.0
  for s,x in pos.items():
   px=ctx['closes'].get(s,{}).get(d,last.get(s,x['entry']))
   if px is not None:last[s]=px
   pv+=x['shares']*last[s]
  return cash+pv,pv
 def add(s,x,d,target_frac):
  nonlocal cash
  eq,_=mark(d); need=max(0,min(x['entry_equity']*target_frac,eq*target_frac)-x['budget']); amt=min(need,cash)
  if amt>1:
   px=ctx['closes'][s][d]; x['shares']+=amt*(1-HALF)/px; x['budget']+=amt; cash-=amt; stats['adds']+=1
   if target_frac>.50:stats['pyramids']+=1
 for d in ctx['dates']:
  for s in list(pos):
   x=pos[s]; t=x['t']; px=ctx['closes'].get(s,{}).get(d)
   if px is None:continue
   last[s]=px
   if d==t['entry_date']:continue
   x['age']+=1; e=t['entry']; x['cum_mfe']=max(x['cum_mfe'],ctx['highs'][s][d]/e-1)
   if t['exit_date']==d:
    xp=ctx['timeout_px'][(s,t['entry_date'])] if t['exit_type']=='timeout' else e*(1+t['gross_return']); cash+=x['shares']*xp*(1-HALF); stats[t['exit_type']]+=1; pos.pop(s); continue
   if not x['flagged']:continue
   cr=px/e-1
   if x['age']==1 and (x['cum_mfe']>=cfg['d1_mfe'] or cr>=cfg['d1_close']):add(s,x,d,cfg['restore_frac']);stats['d1_confirm']+=1
   if x['age']==2 and x['cum_mfe']>=cfg['d2_mfe'] and cr>=cfg['d2_close']:add(s,x,d,cfg['pyramid_frac']);stats['d2_confirm']+=1
  for t in ctx['by'].get(d,[]):
   eq,_=mark(d); f=flag(t,rule); frac=cfg['initial_frac'] if f else .50; budget=min(eq*frac,cash)
   if budget<=1:continue
   cash-=budget;pos[t['symbol']]={'t':t,'entry':t['entry'],'shares':budget*(1-HALF)/t['entry'],'budget':budget,'entry_equity':eq,'flagged':f,'age':0,'cum_mfe':0.0};last[t['symbol']]=t['entry'];stats['flagged_entries']+=int(f)
  eq,pv=mark(d);curve.append({'date':d,'equity':eq,'exposure':pv/eq if eq else 0})
 mdd,pd,td=v58.maxdd(curve); final=curve[-1]['equity']; return {'return':final/INIT-1,'dd':mdd,'final_equity':final,'dd_peak':pd,'dd_trough':td,'trades':len(ctx['arr']),'weekly':v58.weekly(curve),'runtime':dict(stats)}

def edges(m):return {k:{'return_edge_pp':100*(m[k]['return']-FRONTIER[k]['ret']),'dd_improvement_pp':100*(abs(FRONTIER[k]['dd'])-abs(m[k]['dd']))} for k in m}
def strict(m):return all(m[k]['return']>FRONTIER[k]['ret'] and abs(m[k]['dd'])<abs(FRONTIER[k]['dd']) for k in m)

def build_rules(train,periods):
 prim=v513.make_primitives(train); ranked=[]
 for r in prim:
  sc,st=v513.rstats([r],periods);ranked.append((sc,[r],st))
 ranked.sort(key=lambda z:z[0],reverse=True);top=[x[1][0] for x in ranked[:55]];rules=[]
 for r in top:
  sc,st=v513.rstats([r],periods);rules.append((sc,[r],st))
 for a,b in itertools.combinations(top,2):
  if a['f']==b['f']:continue
  sc,st=v513.rstats([a,b],periods);n=sum(v['n'] for v in st.values());stops=sum(v['stops'] for v in st.values())
  if 2<=n<=12 and stops>=2:rules.append((sc,[a,b],st))
 rules.sort(key=lambda z:z[0],reverse=True);return prim,rules[:100]

def main():
 data=load();trades=hz.build(data);train=[t for t in trades if inper(t,TRAIN)];ctx={'2023':prep(data,trades,P23),'2024':prep(data,trades,P24),'final':prep(data,trades,PF)};periods={k:v['arr'] for k,v in ctx.items()};prim,rules=build_rules(train,periods)
 cfgs=[]
 for initial in [.10,.20,.30]:
  for d1m in [.005,.015]:
   for d1c in [0.0,.005]:
    for restore in [.45,.50]:
     for d2m in [.02,.03]:
      for pyr in [.50,.55,.60]:cfgs.append({'initial_frac':initial,'d1_mfe':d1m,'d1_close':d1c,'restore_frac':restore,'d2_mfe':d2m,'d2_close':0.0,'pyramid_frac':pyr})
 rows=[];champs=[]
 for sc,rule,st in rules:
  for cfg in cfgs:
   m={k:simulate(ctx[k],rule,cfg) for k in ctx};e=edges(m);z={'rule':rule,'config':cfg,'diagnostic_score':sc,'flag_profile':st,'metrics':m,'edges':e,'strict_beats_six_frontier':strict(m)};rows.append(z)
   if z['strict_beats_six_frontier']:champs.append(z)
 key=lambda z:(z['strict_beats_six_frontier'],min(v['dd_improvement_pp'] for v in z['edges'].values()),min(v['return_edge_pp'] for v in z['edges'].values()),sum(v['return_edge_pp']+v['dd_improvement_pp'] for v in z['edges'].values()))
 rows.sort(key=key,reverse=True);champs.sort(key=key,reverse=True);best=champs[0] if champs else rows[0]
 res={'version':'v5.14','name':'Staged Surgical Refill','status':'STRICT CHAMPION' if champs else 'NO STRICT CHAMPION','selection_warning':'Historical optimization across already-observed 2023-2026 periods; not pristine out-of-sample.','frontier':FRONTIER,'dataset':{'stocks':len(data),'signals':len(trades),'primitives':len(prim),'rules':len(rules),'configs_per_rule':len(cfgs),'configs_tested':len(rows)},'strict_count':len(champs),'champion':champs[0] if champs else None,'best_near_miss':best,'top20':rows[:20]}
 with open('tmp/egx_backtest/results_v514_staged_surgical_refill.json','w',encoding='utf-8') as f:json.dump(res,f,ensure_ascii=False,indent=2)
 print(json.dumps({'status':res['status'],'strict_count':len(champs),'tested':len(rows),'best':best},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
