import glob,json,math,os,sys,time
from collections import Counter
from datetime import datetime
import pandas as pd
import yfinance as yf

sys.path.insert(0,'tmp/egx_backtest')
import backtest_v3_ml as v3
import live_v517_shadow_scanner as frozen

# Experimental timeframe transplant only. The DAILY v5.17 model itself stays frozen and untouched.
EXPERIMENT='v5.17-H1-literal-transplant'
FROZEN_COMMIT='236519236da35fa19dfd4dc02b1cd332f8c4b0c9'
WEEK_START='2026-08-30'
WEEK_END='2026-09-03'
DOWNLOAD_START='2026-05-01'
DOWNLOAD_END='2026-09-05'  # exclusive
INTERVAL='60m'
OUT='tmp/egx_backtest/results_v517_h1_lastweek.json'


def finite(x):
    try:return x is not None and math.isfinite(float(x))
    except:return False

def symbols_from_reference_repo():
    return sorted({os.path.basename(fp).rsplit('.',1)[0].upper() for fp in glob.glob('egxdata/Dataset/raw/*/*.csv')})

def pick_sub(df,ticker,n):
    if df is None or len(df)==0:return None
    if isinstance(df.columns,pd.MultiIndex):
        l0=list(df.columns.get_level_values(0)); l1=list(df.columns.get_level_values(1))
        if ticker in l0:return df[ticker].copy()
        if ticker in l1:return df.xs(ticker,level=1,axis=1).copy()
        return None
    return df.copy() if n==1 else None

def cairo_ts(idx):
    ts=pd.Timestamp(idx)
    try:
        if ts.tzinfo is None:
            # yfinance intraday indexes are normally timezone-aware. This fallback is only defensive.
            ts=ts.tz_localize('UTC')
        ts=ts.tz_convert('Africa/Cairo')
    except Exception:
        pass
    return ts

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
        ts=cairo_ts(idx)
        out.append({
            'date':ts.isoformat(),
            'session_date':ts.date().isoformat(),
            'time':ts.strftime('%H:%M'),
            'open':o,'high':h,'low':l,'close':c,'volume':v
        })
    ded={r['date']:r for r in out}
    return [ded[k] for k in sorted(ded)]

def download(symbols):
    data={}; failed=[]
    for j in range(0,len(symbols),25):
        ss=symbols[j:j+25]; tt=[s+'.CA' for s in ss]; df=None; err=None
        for attempt in range(3):
            try:
                df=yf.download(tt,start=DOWNLOAD_START,end=DOWNLOAD_END,interval=INTERVAL,auto_adjust=True,actions=False,group_by='ticker',threads=True,prepost=False,progress=False,timeout=30)
                err=None; break
            except Exception as e:
                err=repr(e); time.sleep(2*(attempt+1))
        for s,t in zip(ss,tt):
            rows=rows_from_sub(pick_sub(df,t,len(ss))) if df is not None else []
            week_rows=[r for r in rows if WEEK_START<=r['session_date']<=WEEK_END]
            if len(rows)>=100 and week_rows:
                data[s]=rows
            else:
                failed.append({'symbol':s,'rows':len(rows),'week_rows':len(week_rows),'last':rows[-1]['date'] if rows else None,'error':err})
    return data,failed

def scan_symbol(symbol,rows,market):
    sigs=[]; next_allowed=60; t=60
    while t<len(rows):
        if t<next_allowed:
            t+=1; continue
        matches=[]
        for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
            c=v3.v1_candidate(rows,t,n)
            if c:matches.append(c)
        if matches:
            c=max(matches,key=lambda x:x['base_n'])
            s=frozen.live_features(symbol,rows,t,c,market)
            # Preserve exact frozen v2 filter and exact frozen three-atom gate.
            if s['v2_flag']>0:
                s['session_date']=rows[t]['session_date']; s['time']=rows[t]['time']
                s['bar_timestamp']=rows[t]['date']
                if WEEK_START<=s['session_date']<=WEEK_END:
                    sigs.append(s)
            next_allowed=t+11
        t+=1
    return sigs

def main():
    symbols=symbols_from_reference_repo(); data,failed=download(symbols)
    if len(data)<80:
        raise RuntimeError(f'Hourly coverage too low: {len(data)}/{len(symbols)}')

    market=v3.build_market_maps(data)
    signals=[]
    for sym,rows in data.items():
        signals.extend(scan_symbol(sym,rows,market))
    signals.sort(key=lambda x:(x['bar_timestamp'],-x['median_base_value'],x['symbol']))

    allow=[s for s in signals if s['v517_gate']=='ALLOW']
    reject=[s for s in signals if s['v517_gate']=='REJECT']
    by_day=[]
    for d in sorted(set(r['session_date'] for rows in data.values() for r in rows if WEEK_START<=r['session_date']<=WEEK_END)):
        a=[s for s in allow if s['session_date']==d]; r=[s for s in reject if s['session_date']==d]
        by_day.append({'date':d,'allowed_count':len(a),'rejected_count':len(r),'allowed':[{'time':x['time'],'symbol':x['symbol'],'close':x['entry'],'stop':x['research_stop_price'],'target':x['research_target_price']} for x in a],'rejected':[{'time':x['time'],'symbol':x['symbol'],'close':x['entry'],'matched_atoms':x['matched_atoms']} for x in r]})

    all_week_bars=sum(1 for rows in data.values() for r in rows if WEEK_START<=r['session_date']<=WEEK_END)
    result={
      'experiment':EXPERIMENT,
      'timeframe':'1h',
      'period':[WEEK_START,WEEK_END],
      'frozen_daily_source_commit':FROZEN_COMMIT,
      'rules_changed':False,
      'important_caveat':'This is a literal application of DAILY v5.17 numeric rules to 1-hour bars. The timeframe change itself is material, so this is an experimental diagnostic and is NOT the frozen daily v5.17 strategy or a validated H1 strategy.',
      'data':{
        'reference_symbols':len(symbols),'usable_symbols':len(data),'coverage_ratio':len(data)/len(symbols),
        'failed_or_insufficient_count':len(failed),'hourly_bars_in_week_across_universe':all_week_bars,
        'download_start':DOWNLOAD_START,'download_end_exclusive':DOWNLOAD_END,'source':'Yahoo Finance .CA 60m auto_adjust=True'
      },
      'summary':{
        'candidates_total':len(signals),'allowed_opportunities':len(allow),'rejected_by_v517_gate':len(reject),
        'days_with_allowed':len(set(s['session_date'] for s in allow)),'unique_allowed_symbols':len(set(s['symbol'] for s in allow))
      },
      'allowed_opportunities':[
        {'timestamp':s['bar_timestamp'],'date':s['session_date'],'time':s['time'],'symbol':s['symbol'],'signal_close':s['entry'],'research_stop_price':s['research_stop_price'],'research_target_price':s['research_target_price'],'median_base_value':s['median_base_value'],'rs20':s['rs20'],'market5_ret':s['market5_ret'],'lift':s['lift'],'gap':s['gap'],'compression_ratio':s['compression_ratio']}
        for s in allow
      ],
      'rejected_signals':[
        {'timestamp':s['bar_timestamp'],'date':s['session_date'],'time':s['time'],'symbol':s['symbol'],'signal_close':s['entry'],'matched_atoms':s['matched_atoms']}
        for s in reject
      ],
      'by_day':by_day,
      'failed_sample':failed[:30]
    }
    with open(OUT,'w',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
