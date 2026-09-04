import glob,json,math,os,sys,time
from collections import Counter
from datetime import date,timedelta
import pandas as pd
import yfinance as yf

sys.path.insert(0,'tmp/egx_backtest')
import backtest_v3_ml as v3

FROZEN_COMMIT='236519236da35fa19dfd4dc02b1cd332f8c4b0c9'
ATOMS=[
 [
  {'f':'rs20','side':'high','thr':0.07340059829329726},
  {'f':'market5_ret','side':'high','thr':0.008543451793102896},
 ],
 [
  {'f':'lift','side':'high','thr':0.05965902346208485},
  {'f':'gap','side':'low','thr':-3.413044438183023e-08},
 ],
 [
  {'f':'lift','side':'low','thr':0.04764147846387261},
  {'f':'compression_ratio','side':'high','thr':1.139118181416062},
 ],
]
HALF_FRICTION=0.0025
RESEARCH_STOP=0.045
RESEARCH_TARGET=0.12
HOLD_SESSIONS=7
MAX_POSITIONS=2


def finite(x):
 try:return x is not None and math.isfinite(float(x))
 except:return False

def symbols_from_reference_repo():
 return sorted({os.path.basename(fp).rsplit('.',1)[0].upper() for fp in glob.glob('egxdata/Dataset/raw/*/*.csv')})

def pick_sub(df,ticker,n):
 if df is None or len(df)==0:return None
 if isinstance(df.columns,pd.MultiIndex):
  l0=list(df.columns.get_level_values(0));l1=list(df.columns.get_level_values(1))
  if ticker in l0:return df[ticker].copy()
  if ticker in l1:return df.xs(ticker,level=1,axis=1).copy()
  return None
 return df.copy() if n==1 else None

def rows_from_sub(sub):
 if sub is None or len(sub)==0:return []
 sub=sub.rename(columns={c:str(c).title() for c in sub.columns})
 need=['Open','High','Low','Close','Volume']
 if not all(c in sub.columns for c in need):return []
 out=[]
 for idx,r in sub.iterrows():
  vals=[r.get(c) for c in need]
  if not all(finite(v) for v in vals):continue
  o,h,l,c,v=map(float,vals)
  if min(o,h,l,c)<=0 or v<0:continue
  out.append({'date':pd.Timestamp(idx).date().isoformat(),'open':o,'high':h,'low':l,'close':c,'volume':v})
 ded={r['date']:r for r in out};return [ded[d] for d in sorted(ded)]

def download(symbols):
 start=(date.today()-timedelta(days=500)).isoformat();end=(date.today()+timedelta(days=1)).isoformat()
 data={};failed=[]
 for j in range(0,len(symbols),35):
  ss=symbols[j:j+35];tt=[s+'.CA' for s in ss];df=None;err=None
  for a in range(3):
   try:
    df=yf.download(tt,start=start,end=end,auto_adjust=True,actions=False,group_by='ticker',threads=True,progress=False,timeout=30);err=None;break
   except Exception as e:err=repr(e);time.sleep(2*(a+1))
  for s,t in zip(ss,tt):
   rows=rows_from_sub(pick_sub(df,t,len(ss))) if df is not None else []
   if len(rows)>=100:data[s]=rows
   else:failed.append({'symbol':s,'rows':len(rows),'error':err})
 return data,failed,start,end

def atom_match(s,atom):
 for cond in atom:
  x=s.get(cond['f'])
  if not finite(x):return False
  if cond['side']=='high' and not x>=cond['thr']:return False
  if cond['side']=='low' and not x<=cond['thr']:return False
 return True

def live_features(symbol,rows,t,c,market):
 br=rows[t];prev=rows[t-1];rng=max(br['high']-br['low'],1e-12)
 body=(br['close']-br['open'])/br['open'];clv=(br['close']-br['low'])/rng
 breakout_ret=br['close']/prev['close']-1;gap=br['open']/prev['close']-1;clearance=br['close']/c['base_high']-1
 vol_ratio=br['volume']/c['med_vol'] if c['med_vol']>0 else 0;pre20=prev['close']/rows[t-20]['close']-1 if t>=20 and rows[t-20]['close']>0 else 0
 market5=market['m5'].get(br['date'],0);market20=market['m20'].get(br['date'],0);rs20=pre20-market20
 base=c['base'];ranges=[(x['high']-x['low'])/x['close'] for x in base if x['close']>0];late=v3.mean(ranges[-3:]);early=v3.mean(ranges[:-3]) if len(ranges)>3 else late
 compression=late/early if early and early>0 else 99
 s={'symbol':symbol,'date':br['date'],'entry':br['close'],'base_n':c['base_n'],'base_range':c['range_pct'],'lift':c['lift'],'body':body,'clv':clv,
    'breakout_ret':breakout_ret,'gap':gap,'clearance':clearance,'breakout_vol_ratio':vol_ratio,'pre20_ret':pre20,'compression_ratio':compression,
    'median_base_value':c['median_base_value'],'market5_ret':market5,'market20_ret':market20,'rs20':rs20}
 s['v2_flag']=1.0 if v3.v2_pass(s) else 0.0
 s['matched_atoms']=[i+1 for i,a in enumerate(ATOMS) if atom_match(s,a)]
 s['v517_gate']='REJECT' if s['matched_atoms'] else 'ALLOW'
 s['research_stop_price']=s['entry']*(1-RESEARCH_STOP);s['research_target_price']=s['entry']*(1+RESEARCH_TARGET)
 return s

def current_signal(symbol,rows,scan_date,market):
 # Reproduce frozen cooldown logic without future outcome dependency.
 nxt=60;t=60;found=None
 while t<len(rows):
  if rows[t]['date']>scan_date:break
  if t<nxt:t+=1;continue
  matches=[]
  for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
   c=v3.v1_candidate(rows,t,n)
   if c:matches.append(c)
  if matches:
   c=max(matches,key=lambda x:x['base_n']);s=live_features(symbol,rows,t,c,market)
   if rows[t]['date']==scan_date and s['v2_flag']>0:found=s
   nxt=t+11
  t+=1
 return found

def main():
 syms=symbols_from_reference_repo();data,failed,start,end=download(syms)
 if len(data)<120:raise RuntimeError(f'coverage too low: {len(data)}/{len(syms)}')
 latests=[rows[-1]['date'] for rows in data.values()];counts=Counter(latests);scan_date=counts.most_common(1)[0][0]
 market=v3.build_market_maps(data);cands=[]
 for s,rows in data.items():
  if not any(r['date']==scan_date for r in rows):continue
  x=current_signal(s,rows,scan_date,market)
  if x:cands.append(x)
 cands.sort(key=lambda x:(-x['median_base_value'],x['symbol']))
 allow=[x for x in cands if x['v517_gate']=='ALLOW'];reject=[x for x in cands if x['v517_gate']=='REJECT']
 top_if_flat=allow[:MAX_POSITIONS]
 result={
  'mode':'SHADOW_ONLY','frozen_commit':FROZEN_COMMIT,'scan_date':scan_date,'generated_utc':pd.Timestamp.utcnow().isoformat(),
  'data':{'reference_symbols':len(syms),'usable_symbols':len(data),'coverage_ratio':len(data)/len(syms),'modal_latest_date_count':counts[scan_date],'download_start':start,'download_end_exclusive':end,'failed_count':len(failed)},
  'frozen_rules':{'target_pct':RESEARCH_TARGET,'stop_pct':RESEARCH_STOP,'hold_sessions':HOLD_SESSIONS,'max_positions':MAX_POSITIONS,'atoms':ATOMS},
  'candidates_total':len(cands),'allowed_count':len(allow),'rejected_count':len(reject),'allowed':allow,'rejected':reject,
  'top_two_if_no_existing_positions':top_if_flat,
  'execution_warning':'Research entry is the breakout-session close. This scanner is shadow-only until next-session execution/slippage is separately validated; do not treat research close as a guaranteed live fill.'
 }
 with open('tmp/egx_backtest/live_v517_shadow_scan.json','w',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
