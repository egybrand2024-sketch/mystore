import glob,json,math,os,sys,time
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from curl_cffi import requests

sys.path.insert(0,'tmp/egx_backtest')
import backtest_v3_ml as v3
import live_v517_shadow_scanner as frozen

EXPERIMENT='v5.17-H1-literal-transplant'
FROZEN_COMMIT='236519236da35fa19dfd4dc02b1cd332f8c4b0c9'
WEEK_START='2026-08-30'
WEEK_END='2026-09-03'
DOWNLOAD_START='2026-05-01'
DOWNLOAD_END='2026-09-05'
INTERVAL='60m'
OUT='tmp/egx_backtest/results_v517_h1_lastweek.json'
CAIRO=ZoneInfo('Africa/Cairo')


def finite(x):
    try:return x is not None and math.isfinite(float(x))
    except:return False

def symbols_from_reference_repo():
    return sorted({os.path.basename(fp).rsplit('.',1)[0].upper() for fp in glob.glob('egxdata/Dataset/raw/*/*.csv')})

def epoch(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())

def fetch_hourly(symbol):
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.CA'
    params={'period1':epoch(DOWNLOAD_START),'period2':epoch(DOWNLOAD_END),'interval':INTERVAL,'includePrePost':'false','events':'div,splits'}
    last_err=None
    for attempt in range(4):
        try:
            r=requests.get(url,params=params,impersonate='chrome',timeout=30)
            if r.status_code!=200:
                last_err=f'HTTP {r.status_code}: {r.text[:120]}';time.sleep(1+attempt);continue
            obj=r.json(); res=((obj.get('chart') or {}).get('result') or [])
            if not res:
                last_err=str((obj.get('chart') or {}).get('error'));time.sleep(1+attempt);continue
            z=res[0];ts=z.get('timestamp') or [];q=((z.get('indicators') or {}).get('quote') or [{}])[0]
            opens=q.get('open') or []; highs=q.get('high') or []; lows=q.get('low') or []; closes=q.get('close') or []; vols=q.get('volume') or []
            rows=[]
            for i,t in enumerate(ts):
                vals=[opens[i] if i<len(opens) else None,highs[i] if i<len(highs) else None,lows[i] if i<len(lows) else None,closes[i] if i<len(closes) else None,vols[i] if i<len(vols) else None]
                if not all(finite(v) for v in vals):continue
                o,h,l,c,v=map(float,vals)
                if min(o,h,l,c)<=0 or v<0:continue
                dt=datetime.fromtimestamp(int(t),tz=timezone.utc).astimezone(CAIRO)
                rows.append({'date':dt.isoformat(),'session_date':dt.date().isoformat(),'time':dt.strftime('%H:%M'),'open':o,'high':h,'low':l,'close':c,'volume':v})
            ded={x['date']:x for x in rows}
            return [ded[k] for k in sorted(ded)],None
        except Exception as e:
            last_err=repr(e);time.sleep(1+attempt)
    return [],last_err

def download(symbols):
    data={};failed=[]
    for k,s in enumerate(symbols,1):
        rows,err=fetch_hourly(s)
        wr=[r for r in rows if WEEK_START<=r['session_date']<=WEEK_END]
        if len(rows)>=100 and wr:data[s]=rows
        else:failed.append({'symbol':s,'rows':len(rows),'week_rows':len(wr),'last':rows[-1]['date'] if rows else None,'error':err})
        if k%25==0:print(f'FETCHED {k}/{len(symbols)} usable={len(data)}',flush=True)
    return data,failed

def scan_symbol(symbol,rows,market):
    sigs=[];next_allowed=60;t=60
    while t<len(rows):
        if t<next_allowed:t+=1;continue
        matches=[]
        for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
            c=v3.v1_candidate(rows,t,n)
            if c:matches.append(c)
        if matches:
            c=max(matches,key=lambda x:x['base_n'])
            s=frozen.live_features(symbol,rows,t,c,market)
            if s['v2_flag']>0:
                s['session_date']=rows[t]['session_date'];s['time']=rows[t]['time'];s['bar_timestamp']=rows[t]['date']
                if WEEK_START<=s['session_date']<=WEEK_END:sigs.append(s)
            next_allowed=t+11
        t+=1
    return sigs

def main():
    symbols=symbols_from_reference_repo();data,failed=download(symbols)
    if len(data)<80:raise RuntimeError(f'Hourly coverage too low: {len(data)}/{len(symbols)}')
    market=v3.build_market_maps(data);signals=[]
    for sym,rows in data.items():signals.extend(scan_symbol(sym,rows,market))
    signals.sort(key=lambda x:(x['bar_timestamp'],-x['median_base_value'],x['symbol']))
    allow=[s for s in signals if s['v517_gate']=='ALLOW'];reject=[s for s in signals if s['v517_gate']=='REJECT']
    session_dates=sorted(set(r['session_date'] for rows in data.values() for r in rows if WEEK_START<=r['session_date']<=WEEK_END))
    by_day=[]
    for d in session_dates:
        a=[s for s in allow if s['session_date']==d];rr=[s for s in reject if s['session_date']==d]
        by_day.append({'date':d,'allowed_count':len(a),'rejected_count':len(rr),'allowed':[{'time':x['time'],'symbol':x['symbol'],'close':x['entry'],'stop':x['research_stop_price'],'target':x['research_target_price']} for x in a],'rejected':[{'time':x['time'],'symbol':x['symbol'],'close':x['entry'],'matched_atoms':x['matched_atoms']} for x in rr]})
    result={
      'experiment':EXPERIMENT,'timeframe':'1h','period':[WEEK_START,WEEK_END],'frozen_daily_source_commit':FROZEN_COMMIT,
      'rules_changed':False,
      'important_caveat':'Literal DAILY v5.17 numeric rules applied to 1-hour bars. The timeframe change is material, so this is an experimental diagnostic, not the frozen daily strategy and not a validated H1 strategy.',
      'data':{'reference_symbols':len(symbols),'usable_symbols':len(data),'coverage_ratio':len(data)/len(symbols),'failed_or_insufficient_count':len(failed),'hourly_bars_in_week_across_universe':sum(1 for rows in data.values() for r in rows if WEEK_START<=r['session_date']<=WEEK_END),'download_start':DOWNLOAD_START,'download_end_exclusive':DOWNLOAD_END,'source':'Yahoo Finance chart API .CA interval=60m; raw OHLC'},
      'summary':{'candidates_total':len(signals),'allowed_opportunities':len(allow),'rejected_by_v517_gate':len(reject),'days_with_allowed':len(set(s['session_date'] for s in allow)),'unique_allowed_symbols':len(set(s['symbol'] for s in allow))},
      'allowed_opportunities':[{'timestamp':s['bar_timestamp'],'date':s['session_date'],'time':s['time'],'symbol':s['symbol'],'signal_close':s['entry'],'research_stop_price':s['research_stop_price'],'research_target_price':s['research_target_price'],'median_base_value':s['median_base_value'],'rs20':s['rs20'],'market5_ret':s['market5_ret'],'lift':s['lift'],'gap':s['gap'],'compression_ratio':s['compression_ratio']} for s in allow],
      'rejected_signals':[{'timestamp':s['bar_timestamp'],'date':s['session_date'],'time':s['time'],'symbol':s['symbol'],'signal_close':s['entry'],'matched_atoms':s['matched_atoms']} for s in reject],
      'by_day':by_day,'failed_sample':failed[:40]
    }
    with open(OUT,'w',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
