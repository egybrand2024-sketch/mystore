import glob,json,math,os,sys,time
from datetime import date,datetime,timedelta
import pandas as pd
import yfinance as yf

sys.path.insert(0,'tmp/egx_backtest')
import analyze_v58_hazard_attribution as hz
import backtest_v513_surgical_gate as v513
import backtest_v515_ensemble_surgical_gate as v515

FROZEN_COMMIT='236519236da35fa19dfd4dc02b1cd332f8c4b0c9'
FROZEN_BRANCH='frozen-egx-defensive-lift-v517-20260904'
SOURCE_UNIVERSE='mohamedredasafan1/dataroom Dataset/raw symbol list'
DATA_START='2025-09-01'      # fresh Yahoo history for clean warm-up; no stitch to old adjusted prices
OOS_START='2026-02-05'       # strictly after old dataset max 2026-02-04
DOWNLOAD_END='2026-09-05'    # yfinance end is exclusive; includes 2026-09-04 if Yahoo has it
INIT=100000.0

# EXACT frozen v5.17 reject ensemble. No thresholds are recomputed from the fresh data.
ATOMS=[
 [
  {'f':'rs20','side':'high','thr':0.07340059829329726,'q':0.75},
  {'f':'market5_ret','side':'high','thr':0.008543451793102896,'q':0.70},
 ],
 [
  {'f':'lift','side':'high','thr':0.05965902346208485,'q':0.75},
  {'f':'gap','side':'low','thr':-3.413044438183023e-08,'q':0.15},
 ],
 [
  {'f':'lift','side':'low','thr':0.04764147846387261,'q':0.30},
  {'f':'compression_ratio','side':'high','thr':1.139118181416062,'q':0.85},
 ],
]

def finite(x):
 try:return x is not None and math.isfinite(float(x))
 except:return False

def symbols_from_reference_repo():
 fps=sorted(glob.glob('egxdata/Dataset/raw/*/*.csv'))
 return sorted({os.path.basename(fp).rsplit('.',1)[0].upper() for fp in fps})

def pick_sub(df,ticker,batch_len):
 if df is None or len(df)==0:return None
 if isinstance(df.columns,pd.MultiIndex):
  l0=list(df.columns.get_level_values(0)); l1=list(df.columns.get_level_values(1))
  if ticker in l0:
   return df[ticker].copy()
  if ticker in l1:
   return df.xs(ticker,level=1,axis=1).copy()
  return None
 return df.copy() if batch_len==1 else None

def rows_from_sub(sub):
 if sub is None or len(sub)==0:return []
 # Normalize potential field case/multiindex artifacts.
 sub=sub.rename(columns={c:str(c).title() for c in sub.columns})
 need=['Open','High','Low','Close','Volume']
 if not all(c in sub.columns for c in need):return []
 out=[]
 for idx,r in sub.iterrows():
  vals=[r.get(c) for c in need]
  if not all(finite(v) for v in vals):continue
  o,h,l,c,v=map(float,vals)
  if min(o,h,l,c)<=0 or v<0:continue
  d=pd.Timestamp(idx).date().isoformat()
  out.append({'date':d,'open':o,'high':h,'low':l,'close':c,'volume':v})
 ded={r['date']:r for r in out}
 return [ded[d] for d in sorted(ded)]

def download_fresh(symbols):
 data={};failed=[]; batches=[]; batch_size=35
 for j in range(0,len(symbols),batch_size):
  syms=symbols[j:j+batch_size]; tickers=[s+'.CA' for s in syms]
  err=None; df=None
  for attempt in range(3):
   try:
    df=yf.download(tickers,start=DATA_START,end=DOWNLOAD_END,auto_adjust=True,actions=False,group_by='ticker',threads=True,progress=False,timeout=30)
    err=None;break
   except Exception as e:
    err=repr(e);time.sleep(2*(attempt+1))
  batches.append({'symbols':len(syms),'error':err})
  for s,t in zip(syms,tickers):
   rows=rows_from_sub(pick_sub(df,t,len(syms))) if df is not None else []
   if len(rows)>=100 and any(r['date']>=OOS_START for r in rows):data[s]=rows
   else:failed.append({'symbol':s,'rows':len(rows),'last_date':rows[-1]['date'] if rows else None})
 return data,failed,batches

def summarize_outcomes(arr):
 return {'n':len(arr),'targets':sum(t['exit_type']=='target' for t in arr),'stops':sum(t['exit_type']=='stop' for t in arr),'timeouts':sum(t['exit_type']=='timeout' for t in arr)}

def flagged_profile(arr):
 x=[t for t in arr if v515.ens_flag(t,ATOMS)]
 return {
  'n':len(x),'targets':sum(t['exit_type']=='target' for t in x),'stops':sum(t['exit_type']=='stop' for t in x),'timeouts':sum(t['exit_type']=='timeout' for t in x),
  'trades':[{'symbol':t['symbol'],'entry_date':t['entry_date'],'exit_date':t['exit_date'],'exit_type':t['exit_type'],'gross_return':t['gross_return'],
             'matched_atoms':[i+1 for i,a in enumerate(ATOMS) if v515.atom_flag(t,a)]} for t in x]
 }

def main():
 symbols=symbols_from_reference_repo();data,failed,batches=download_fresh(symbols)
 if not data:raise RuntimeError('No fresh Yahoo EGX data downloaded')
 latest=max(r[-1]['date'] for r in data.values()); earliest=min(r[0]['date'] for r in data.values())
 recent_cut=(datetime.fromisoformat(latest).date()-timedelta(days=7)).isoformat()
 recent_coverage=sum(r[-1]['date']>=recent_cut for r in data.values())
 coverage_ratio=len(data)/len(symbols) if symbols else 0
 if len(data)<120:raise RuntimeError(f'Fresh-data coverage too low: {len(data)}/{len(symbols)}')

 # Build DLP signals only from the freshly downloaded, internally consistent Yahoo-adjusted history.
 trades=hz.build(data)
 period=(OOS_START,latest)
 ctx=v513.prep_ctx(data,trades,period)
 arr=ctx['arr']
 baseline=v515.portfolio(ctx,[],0.0)        # exact 50% v3.2 mechanics on same accepted-trade set
 frozen=v515.portfolio(ctx,ATOMS,0.0)      # exact frozen v5.17: reject any accepted trade matching any atom
 fp=flagged_profile(arr)

 ret_edge=100*(frozen['return']-baseline['return'])
 dd_edge=100*(abs(baseline['dd'])-abs(frozen['dd']))
 strict_better=frozen['return']>baseline['return'] and abs(frozen['dd'])<abs(baseline['dd'])
 no_worse=frozen['return']>=baseline['return'] and abs(frozen['dd'])<=abs(baseline['dd'])
 sample_status='ADEQUATE_PRELIMINARY' if len(arr)>=15 else ('SMALL_SAMPLE' if len(arr)>=5 else 'VERY_SMALL_SAMPLE')
 evidence='PASS_STRICT_VS_V32' if strict_better else ('PASS_NO_WORSE' if no_worse else 'FAIL_VS_V32')
 if fp['n']==0:evidence='INCONCLUSIVE_NO_GATE_TRIGGERS' if no_worse else evidence

 result={
  'version':'v5.17-FROZEN-OOS-1',
  'frozen_model':{'commit':FROZEN_COMMIT,'branch':FROZEN_BRANCH,'atoms':ATOMS,'rule':'reject accepted v3.2 trade if ANY atom matches; no replacement trade is admitted'},
  'protocol':{
   'old_research_data_max':'2026-02-04','oos_start':OOS_START,'data_warmup_start':DATA_START,'download_end_exclusive':DOWNLOAD_END,
   'source':'Yahoo Finance via yfinance, .CA tickers, auto_adjust=True','selection_or_tuning_on_oos':False,
   'same_bar_policy':'unchanged from frozen v3.2 signal outcome builder: stop-first','round_trip_friction_sensitivity':0.005,
   'decision_rule':'Compare frozen v5.17 with v3.2 on exactly the same fresh accepted-trade set. Strict pass requires higher return AND lower absolute max drawdown.'
  },
  'data_quality':{
   'reference_symbol_count':len(symbols),'downloaded_usable_symbols':len(data),'coverage_ratio':coverage_ratio,'recent_7_calendar_day_coverage':recent_coverage,
   'earliest_fresh_date':earliest,'latest_fresh_date':latest,'failed_or_insufficient_count':len(failed),'failed_or_insufficient':failed,'batches':batches
  },
  'sample':{'status':sample_status,'closed_accepted_trades':len(arr),'accepted_outcomes':summarize_outcomes(arr),'latest_closed_entry_date':max([t['entry_date'] for t in arr],default=None),'signals_built_total_with_warmup':len(trades)},
  'v32_baseline':baseline,
  'v517_frozen':frozen,
  'gate_oos_profile':fp,
  'comparison':{'return_edge_percentage_points':ret_edge,'dd_improvement_percentage_points':dd_edge,'strict_better_than_v32':strict_better,'no_worse_than_v32':no_worse,'evidence_status':evidence},
  'interpretation_guardrails':[
   'No v5.17 threshold, atom, target, stop, horizon, slot count, sizing rule or friction assumption was changed after seeing OOS data.',
   'The fresh period begins after the old dataset maximum date, so these prices were not used to design v5.17.',
   'This is one OOS window, not a guarantee of future performance; sample size and number of gate triggers must be considered.',
   'Yahoo adjusted history is freshly downloaded from 2025-09-01 to avoid stitching old and newly adjusted price series.'
  ]
 }
 with open('tmp/egx_backtest/results_v517_frozen_oos_fresh.json','w',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
 print(json.dumps({'data_quality':result['data_quality'],'sample':result['sample'],'v32':baseline,'v517':frozen,'gate':fp,'comparison':result['comparison']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
