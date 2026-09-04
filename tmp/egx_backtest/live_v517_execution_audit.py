import glob,json,os,time
from datetime import datetime,timedelta
import pandas as pd
import yfinance as yf

OUT='tmp/egx_backtest/live_v517_execution_audit.json'
HIST='tmp/egx_backtest/live_v517_shadow_history/scan_*.json'
FROZEN_COMMIT='236519236da35fa19dfd4dc02b1cd332f8c4b0c9'

def load_existing():
 if os.path.exists(OUT):
  try:return json.load(open(OUT,'r',encoding='utf-8'))
  except:pass
 return {'mode':'EXECUTION_AUDIT_ONLY','frozen_commit':FROZEN_COMMIT,'records':[]}

def collect_signals():
 out={}
 for fp in sorted(glob.glob(HIST)):
  try:s=json.load(open(fp,'r',encoding='utf-8'))
  except:continue
  for x in s.get('allowed',[]):
   key=f"{x['symbol']}|{x['date']}"
   out[key]={'symbol':x['symbol'],'signal_date':x['date'],'research_close':x['entry'],'research_stop':x['research_stop_price'],'research_target':x['research_target_price'],'matched_atoms':x.get('matched_atoms',[])}
 return out

def fetch_rows(symbol,start,end):
 t=symbol+'.CA'
 for a in range(3):
  try:
   df=yf.download(t,start=start,end=end,auto_adjust=True,actions=False,progress=False,threads=False,timeout=30)
   if df is None or len(df)==0:return []
   if isinstance(df.columns,pd.MultiIndex):df=df.xs(t,level=1,axis=1) if t in df.columns.get_level_values(1) else df.droplevel(1,axis=1)
   rows=[]
   for idx,r in df.iterrows():
    rows.append({'date':pd.Timestamp(idx).date().isoformat(),'open':float(r['Open']),'high':float(r['High']),'low':float(r['Low']),'close':float(r['Close'])})
   return rows
  except Exception:
   time.sleep(2*(a+1))
 return []

def main():
 state=load_existing();known={f"{r['symbol']}|{r['signal_date']}":r for r in state.get('records',[])};signals=collect_signals()
 for key,s in signals.items():
  rec=known.get(key,s.copy())
  if rec.get('next_session_open') is None:
   d=datetime.fromisoformat(s['signal_date']).date();rows=fetch_rows(s['symbol'],(d+timedelta(days=1)).isoformat(),(d+timedelta(days=15)).isoformat())
   future=[r for r in rows if r['date']>s['signal_date']]
   if future:
    n=future[0];rec['next_session_date']=n['date'];rec['next_session_open']=n['open'];rec['open_slippage_pct']=n['open']/s['research_close']-1
    rec['open_vs_research_stop_pct']=n['open']/s['research_stop']-1;rec['open_vs_research_target_pct']=n['open']/s['research_target']-1
   else:rec['status']='WAITING_NEXT_SESSION'
  if rec.get('next_session_open') is not None:rec['status']='MEASURED'
  known[key]=rec
 records=sorted(known.values(),key=lambda r:(r['signal_date'],r['symbol']))
 measured=[r for r in records if r.get('next_session_open') is not None];sl=[r['open_slippage_pct'] for r in measured]
 state={'mode':'EXECUTION_AUDIT_ONLY','frozen_commit':FROZEN_COMMIT,'updated_utc':pd.Timestamp.utcnow().isoformat(),'records':records,
        'summary':{'signals':len(records),'measured':len(measured),'waiting':len(records)-len(measured),'avg_open_slippage_pct':sum(sl)/len(sl) if sl else None,'median_open_slippage_pct':float(pd.Series(sl).median()) if sl else None,'max_abs_open_slippage_pct':max((abs(x) for x in sl),default=None)},
        'guardrail':'No live-entry rule is chosen from this file. It only measures next-session execution gap versus the frozen research close.'}
 with open(OUT,'w',encoding='utf-8') as f:json.dump(state,f,ensure_ascii=False,indent=2)
 print(json.dumps(state['summary'],ensure_ascii=False,indent=2))
if __name__=='__main__':main()
