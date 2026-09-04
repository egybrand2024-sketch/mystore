import json,sys
from collections import Counter
sys.path.insert(0,'tmp/egx_backtest')
import live_v517_shadow_scanner as live
import backtest_v3_ml as v3

WEEK_START='2026-08-23'
WEEK_END='2026-08-27'
OUT='tmp/egx_backtest/audit_v517_week_20260823_27.json'


def main():
    syms=live.symbols_from_reference_repo()
    data,failed,start,end=live.download(syms)
    if len(data)<120:
        raise RuntimeError(f'coverage too low: {len(data)}/{len(syms)}')

    market=v3.build_market_maps(data)
    # Market dates are dates represented by a broad cross-section of the universe.
    date_counts=Counter(r['date'] for rows in data.values() for r in rows if WEEK_START<=r['date']<=WEEK_END)
    market_dates=sorted(d for d,n in date_counts.items() if n>=max(100,int(len(data)*0.60)))

    days=[];all_allowed=[];all_rejected=[]
    for d in market_dates:
        cands=[]
        for s,rows in data.items():
            if not any(r['date']==d for r in rows):
                continue
            x=live.current_signal(s,rows,d,market)
            if x:
                cands.append(x)
        cands.sort(key=lambda x:(-x['median_base_value'],x['symbol']))
        allow=[x for x in cands if x['v517_gate']=='ALLOW']
        reject=[x for x in cands if x['v517_gate']=='REJECT']
        all_allowed.extend(allow);all_rejected.extend(reject)
        days.append({
            'date':d,
            'universe_with_bar':date_counts[d],
            'candidates_total':len(cands),
            'allowed_count':len(allow),
            'rejected_count':len(reject),
            'allowed':allow,
            'rejected':reject,
            'top_two_if_flat':allow[:live.MAX_POSITIONS],
        })

    result={
        'audit':'v5.17 frozen prior-week opportunity count',
        'frozen_commit':live.FROZEN_COMMIT,
        'week':[WEEK_START,WEEK_END],
        'rules_unchanged':True,
        'data':{
            'reference_symbols':len(syms),
            'usable_symbols':len(data),
            'coverage_ratio':len(data)/len(syms),
            'download_start':start,
            'download_end_exclusive':end,
            'failed_count':len(failed),
            'market_dates':market_dates,
        },
        'summary':{
            'trading_days_scanned':len(market_dates),
            'candidates_total':len(all_allowed)+len(all_rejected),
            'allowed_opportunities':len(all_allowed),
            'rejected_by_v517_gate':len(all_rejected),
            'days_with_allowed_opportunity':sum(1 for d in days if d['allowed_count']>0),
            'unique_allowed_symbols':len(set(x['symbol'] for x in all_allowed)),
        },
        'allowed_opportunities':[
            {
                'date':x['date'],'symbol':x['symbol'],'signal_close':x['entry'],
                'research_stop_price':x['research_stop_price'],'research_target_price':x['research_target_price'],
                'median_base_value':x['median_base_value'],'matched_atoms':x['matched_atoms']
            } for x in all_allowed
        ],
        'rejected_signals':[
            {'date':x['date'],'symbol':x['symbol'],'signal_close':x['entry'],'matched_atoms':x['matched_atoms']}
            for x in all_rejected
        ],
        'days':days,
        'note':'Opportunity count means frozen v3.2 signal passing v5.17 ALLOW. It is not a recommendation or proof of executable fill at the research close.'
    }
    with open(OUT,'w',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
