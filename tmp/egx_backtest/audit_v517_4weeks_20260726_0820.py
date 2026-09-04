import json,sys
from collections import Counter
from datetime import datetime
sys.path.insert(0,'tmp/egx_backtest')
import live_v517_shadow_scanner as live
import backtest_v3_ml as v3

START='2026-07-26'
END='2026-08-20'
OUT='tmp/egx_backtest/audit_v517_4weeks_20260726_0820.json'
WEEKS=[
 ('W1','2026-07-26','2026-07-30'),
 ('W2','2026-08-02','2026-08-06'),
 ('W3','2026-08-09','2026-08-13'),
 ('W4','2026-08-16','2026-08-20'),
]

def main():
    syms=live.symbols_from_reference_repo()
    data,failed,download_start,download_end=live.download(syms)
    if len(data)<120:
        raise RuntimeError(f'coverage too low: {len(data)}/{len(syms)}')
    market=v3.build_market_maps(data)

    date_counts=Counter(r['date'] for rows in data.values() for r in rows if START<=r['date']<=END)
    min_broad=max(100,int(len(data)*0.60))
    market_dates=sorted(d for d,n in date_counts.items() if n>=min_broad)

    daily=[]; allowed_all=[]; rejected_all=[]
    for d in market_dates:
        cands=[]
        for sym,rows in data.items():
            if not any(r['date']==d for r in rows):
                continue
            x=live.current_signal(sym,rows,d,market)
            if x:
                cands.append(x)
        cands.sort(key=lambda x:(-x['median_base_value'],x['symbol']))
        allow=[x for x in cands if x['v517_gate']=='ALLOW']
        reject=[x for x in cands if x['v517_gate']=='REJECT']
        allowed_all.extend(allow); rejected_all.extend(reject)
        daily.append({
            'date':d,'universe_with_bar':date_counts[d],
            'candidates_total':len(cands),'allowed_count':len(allow),'rejected_count':len(reject),
            'allowed':[{'symbol':x['symbol'],'signal_close':x['entry'],'stop':x['research_stop_price'],'target':x['research_target_price'],'liquidity':x['median_base_value']} for x in allow],
            'rejected':[{'symbol':x['symbol'],'signal_close':x['entry'],'matched_atoms':x['matched_atoms']} for x in reject],
        })

    week_rows=[]
    for label,a,b in WEEKS:
        ds=[x for x in daily if a<=x['date']<=b]
        wa=[x for x in allowed_all if a<=x['date']<=b]
        wr=[x for x in rejected_all if a<=x['date']<=b]
        week_rows.append({
            'week':label,'start':a,'end':b,'trading_days':len(ds),
            'candidates_total':len(wa)+len(wr),'allowed_opportunities':len(wa),'rejected_by_gate':len(wr),
            'days_with_allowed':sum(x['allowed_count']>0 for x in ds),
            'allowed_symbols':[{'date':x['date'],'symbol':x['symbol'],'signal_close':x['entry']} for x in wa],
        })

    allowed_sorted=sorted(allowed_all,key=lambda x:(x['date'],x['symbol']))
    signal_dates=sorted(set(x['date'] for x in allowed_sorted))
    gaps=[]
    for a,b in zip(signal_dates,signal_dates[1:]):
        ai=market_dates.index(a); bi=market_dates.index(b)
        gaps.append({'from':a,'to':b,'trading_day_gap':bi-ai,'calendar_day_gap':(datetime.fromisoformat(b)-datetime.fromisoformat(a)).days})

    result={
      'audit':'v5.17 frozen four-week opportunity frequency',
      'frozen_commit':live.FROZEN_COMMIT,
      'period':[START,END],
      'rules_unchanged':True,
      'data':{
        'reference_symbols':len(syms),'usable_symbols':len(data),'coverage_ratio':len(data)/len(syms),
        'failed_count':len(failed),'download_start':download_start,'download_end_exclusive':download_end,
        'market_dates':market_dates,
      },
      'summary':{
        'trading_days_scanned':len(market_dates),
        'candidates_total':len(allowed_all)+len(rejected_all),
        'allowed_opportunities':len(allowed_all),
        'rejected_by_v517_gate':len(rejected_all),
        'days_with_allowed_opportunity':sum(x['allowed_count']>0 for x in daily),
        'weeks_with_allowed_opportunity':sum(w['allowed_opportunities']>0 for w in week_rows),
        'weeks_without_allowed_opportunity':sum(w['allowed_opportunities']==0 for w in week_rows),
        'unique_allowed_symbols':len(set(x['symbol'] for x in allowed_all)),
        'allowed_per_trading_day':len(allowed_all)/len(market_dates) if market_dates else None,
        'allowed_per_week':len(allowed_all)/4,
      },
      'weeks':week_rows,
      'allowed_opportunities':[
        {'date':x['date'],'symbol':x['symbol'],'signal_close':x['entry'],'research_stop_price':x['research_stop_price'],'research_target_price':x['research_target_price'],'median_base_value':x['median_base_value']}
        for x in allowed_sorted
      ],
      'rejected_signals':[{'date':x['date'],'symbol':x['symbol'],'signal_close':x['entry'],'matched_atoms':x['matched_atoms']} for x in rejected_all],
      'signal_date_gaps':gaps,
      'daily':daily,
      'note':'Opportunity = frozen v3.2 setup that passes the frozen v5.17 gate. This audit counts signals only; it does not assume live fill at the signal close.'
    }
    with open(OUT,'w',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
