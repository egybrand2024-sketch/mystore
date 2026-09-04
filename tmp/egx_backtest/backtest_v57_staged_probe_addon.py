import glob,json,os,sys
from collections import defaultdict
from datetime import datetime,timedelta

sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3
import backtest_v56_early_path_behavior as v56

VAL1=("2023-01-01","2023-12-31")
VAL2=("2024-01-01","2024-12-31")
FINAL=("2025-01-01","2026-02-28")
INITIAL=100000.0
FRICTION=0.005
TARGET=0.12
STOP=0.045
HORIZON=7
SLOTS=2
WEEKLY_TARGET=0.02

PROBE_FRACS=[0.15,0.20,0.25,0.30]
ADD_DAYS=[1,2]
CONFIRM_MODES=["close_ge_entry","close_ge_1pct","mfe_ge_2pct","close_ge_entry_and_mfe_ge_2pct"]
UNCONFIRMED_ACTIONS=["hold_probe","exit_probe"]
MIN_WEALTH_RATIO=0.98
MIN_DD_REDUCTION=0.10
MIN_ACTIVE_GE2_RATIO=0.95
MIN_TRADES=12


def week_start(s):
    d=datetime.fromisoformat(s).date(); return (d-timedelta(days=(d.weekday()+1)%7)).isoformat()

def mean(a): return sum(a)/len(a) if a else 0.0

def maxdd(curve):
    peak=-1; pd=None; mdd=0; ddp=ddt=None
    for r in curve:
        e=r['equity']
        if e>peak: peak=e; pd=r['date']
        dd=e/peak-1 if peak>0 else 0
        if dd<mdd: mdd=dd; ddp=pd; ddt=r['date']
    return mdd,ddp,ddt

def weekly(curve):
    by=defaultdict(list)
    for r in curve: by[week_start(r['date'])].append(r)
    prev=INITIAL; vals=[]; active=[]; hit=0
    for wk in sorted(by):
        arr=by[wk]; end=arr[-1]['equity']; ret=end/prev-1
        vals.append(ret)
        if any(x['exposure']>1e-9 for x in arr): active.append(ret)
        if max(x['equity'] for x in arr)/prev-1>=WEEKLY_TARGET: hit+=1
        prev=end
    return {'weeks':len(vals),'avg':mean(vals),'active_weeks':len(active),'active_avg':mean(active),'active_ge_2_rate':sum(x>=WEEKLY_TARGET for x in active)/len(active) if active else 0,'weekend_ge_2_rate':sum(x>=WEEKLY_TARGET for x in vals)/len(vals) if vals else 0,'hit_2_anytime_rate':hit/len(vals) if vals else 0,'worst':min(vals) if vals else 0,'best':max(vals) if vals else 0}

def confirm(rows,entry_i,day,mode,entry):
    j=entry_i+day
    if j>=len(rows): return False,None,None
    sub=rows[entry_i+1:j+1]
    close=rows[j]['close']
    mfe=max(x['high']/entry-1 for x in sub) if sub else 0
    if mode=='close_ge_entry': ok=close>=entry
    elif mode=='close_ge_1pct': ok=close>=entry*1.01
    elif mode=='mfe_ge_2pct': ok=mfe>=0.02
    elif mode=='close_ge_entry_and_mfe_ge_2pct': ok=(close>=entry and mfe>=0.02)
    else: raise ValueError(mode)
    return ok,j,{'close_ret':close/entry-1,'mfe':mfe}

def build_signal_trades(data):
    market=v3.build_market_maps(data); signals=[]
    for s,rows in data.items(): signals+=v56.collect(s,rows,market)
    out=[]
    for sig in signals:
        rows=data[sig['symbol']]; o=v56.base_outcome(rows,sig)
        if o: out.append({**sig,**o})
    return out,signals

def simulate(base_trades,data,period,cfg=None):
    dates=sorted({r['date'] for rows in data.values() for r in rows if period[0]<=r['date']<=period[1]})
    closes={s:{r['date']:r['close'] for r in rows} for s,rows in data.items()}
    highs={s:{r['date']:r['high'] for r in rows} for s,rows in data.items()}
    lows={s:{r['date']:r['low'] for r in rows} for s,rows in data.items()}
    idxmap={s:{r['date']:i for i,r in enumerate(rows)} for s,rows in data.items()}
    eb=defaultdict(list)
    for tr in base_trades:
        if period[0]<=tr['entry_date']<=period[1] and tr['exit_date']<=period[1]: eb[tr['entry_date']].append(tr)
    for d in eb: eb[d].sort(key=lambda x:(-x['liquidity'],x['symbol']))
    cash=INITIAL; pos={}; last={}; curve=[]; real=[]; skip=defaultdict(int); half=FRICTION/2

    def mark(d):
        pv=0
        for s,q in pos.items():
            px=closes.get(s,{}).get(d,last.get(s,q['entry']))
            if px is not None: last[s]=px
            pv+=q['shares']*last[s]
        return cash+pv,pv

    for d in dates:
        for s in list(pos):
            q=pos[s]; px=closes[s].get(d)
            if px is None: continue
            last[s]=px
            if d==q['entry_date']: continue
            q['age']+=1
            stop_px=q['anchor_entry']*(1-STOP); target_px=q['anchor_entry']*(1+TARGET)
            exit_type=None; exit_px=None
            if lows[s][d]<=stop_px: exit_type='stop'; exit_px=stop_px
            elif highs[s][d]>=target_px: exit_type='target'; exit_px=target_px
            elif q['age']>=HORIZON: exit_type='timeout'; exit_px=px

            if cfg and not q['stage_decided'] and q['age']>=cfg['add_day'] and exit_type is None:
                rows=data[s]; ei=q['entry_index']
                ok,_,diag=confirm(rows,ei,cfg['add_day'],cfg['confirm_mode'],q['anchor_entry'])
                q['stage_decided']=True; q['confirm_diag']=diag; q['confirmed']=ok
                if ok:
                    eq,_=mark(d); target_budget=eq*0.50; add_budget=max(0,min(target_budget-q['budget'],cash))
                    if add_budget>1:
                        add_sh=add_budget*(1-half)/px; cash-=add_budget
                        q['shares']+=add_sh; q['budget']+=add_budget; q['added']=True; q['add_date']=d; q['add_price']=px
                elif cfg['unconfirmed_action']=='exit_probe':
                    exit_type='early_unconfirmed'; exit_px=px

            if exit_type:
                proceeds=q['shares']*exit_px*(1-half); cash+=proceeds
                real.append({'symbol':s,'entry_date':q['entry_date'],'exit_date':d,'exit_type':exit_type,'net_return':proceeds/q['budget']-1,'confirmed':q.get('confirmed',False),'added':q.get('added',False),'probe_frac':q.get('probe_frac',0.5)})
                pos.pop(s)

        for tr in eb.get(d,[]):
            s=tr['symbol']
            if s in pos: skip['duplicate_symbol']+=1; continue
            if len(pos)>=SLOTS: skip['max_positions']+=1; continue
            eq,_=mark(d); frac=0.50 if cfg is None else cfg['probe_frac']; budget=min(eq*frac,cash)
            if budget<=1: skip['cash']+=1; continue
            entry=tr['entry']; shares=budget*(1-half)/entry; cash-=budget
            pos[s]={'shares':shares,'budget':budget,'entry':entry,'anchor_entry':entry,'entry_date':d,'entry_index':idxmap[s][d],'age':0,'stage_decided':cfg is None,'confirmed':cfg is None,'added':False,'probe_frac':frac}
            last[s]=entry

        eq,pv=mark(d); curve.append({'date':d,'equity':eq,'open':len(pos),'exposure':pv/eq if eq else 0})

    mdd,pd,td=maxdd(curve); final=curve[-1]['equity']
    d0=datetime.fromisoformat(curve[0]['date']).date(); d1=datetime.fromisoformat(curve[-1]['date']).date(); yrs=max((d1-d0).days/365.25,1/365.25)
    rs=[x['net_return'] for x in real]
    return {'trades':len(real),'skipped':sum(skip.values()),'skip_reasons':dict(skip),'final_equity':final,'total_return':final/INITIAL-1,'cagr':(final/INITIAL)**(1/yrs)-1,'max_drawdown':mdd,'dd_peak':pd,'dd_trough':td,'avg_trade_return':mean(rs),'positive_trade_rate':sum(x>0 for x in rs)/len(rs) if rs else 0,'added_trades':sum(x.get('added') for x in real),'confirmed_trades':sum(x.get('confirmed') for x in real),'early_unconfirmed_exits':sum(x['exit_type']=='early_unconfirmed' for x in real),'weekly':weekly(curve),'avg_exposure':mean([x['exposure'] for x in curve]),'realized':real,'curve':curve}

def slim(x): return {k:v for k,v in x.items() if k not in {'realized','curve'}}

def main():
    root=os.environ.get('EGX_DATA_ROOT','egxdata/Dataset/raw'); data={}
    for fp in sorted(glob.glob(os.path.join(root,'*','*.csv'))):
        s=os.path.basename(fp).split('.')[0].upper(); rows=v3.load_csv_all(fp)
        if len(rows)>=100: data[s]=rows
    trades,signals=build_signal_trades(data)
    def per(p): return [t for t in trades if p[0]<=t['entry_date']<=p[1] and t['exit_date']<=p[1]]
    b23=simulate(per(VAL1),data,VAL1,None); b24=simulate(per(VAL2),data,VAL2,None); bf=simulate(per(FINAL),data,FINAL,None)
    tested=0; eligible=[]; allrows=[]
    for pf in PROBE_FRACS:
      for ad in ADD_DAYS:
       for cm in CONFIRM_MODES:
        for ua in UNCONFIRMED_ACTIONS:
          tested+=1; cfg={'probe_frac':pf,'add_day':ad,'confirm_mode':cm,'unconfirmed_action':ua}
          a=simulate(per(VAL1),data,VAL1,cfg); b=simulate(per(VAL2),data,VAL2,cfg)
          if a['trades']<MIN_TRADES or b['trades']<MIN_TRADES: continue
          wr1=(1+a['total_return'])/(1+b23['total_return']); wr2=(1+b['total_return'])/(1+b24['total_return'])
          dr1=1-abs(a['max_drawdown'])/abs(b23['max_drawdown']); dr2=1-abs(b['max_drawdown'])/abs(b24['max_drawdown'])
          ar1=a['weekly']['active_ge_2_rate']/b23['weekly']['active_ge_2_rate'] if b23['weekly']['active_ge_2_rate'] else 1
          ar2=b['weekly']['active_ge_2_rate']/b24['weekly']['active_ge_2_rate'] if b24['weekly']['active_ge_2_rate'] else 1
          row={'config':cfg,'2023':slim(a),'2024':slim(b),'min_wealth_ratio':min(wr1,wr2),'min_dd_reduction':min(dr1,dr2),'min_active_ge2_ratio':min(ar1,ar2),'min_cagr':min(a['cagr'],b['cagr'])}
          allrows.append(row)
          if row['min_wealth_ratio']>=MIN_WEALTH_RATIO and row['min_dd_reduction']>=MIN_DD_REDUCTION and row['min_active_ge2_ratio']>=MIN_ACTIVE_GE2_RATIO: eligible.append(row)
    eligible.sort(key=lambda z:(z['min_wealth_ratio'],z['min_dd_reduction'],z['min_active_ge2_ratio'],z['min_cagr']),reverse=True)
    allrows.sort(key=lambda z:(z['min_wealth_ratio'],z['min_dd_reduction'],z['min_active_ge2_ratio']),reverse=True)
    best=eligible[0] if eligible else None
    fin=simulate(per(FINAL),data,FINAL,best['config']) if best else None
    result={'pattern':'Defensive Lift v5.7 Staged Probe + Add-on','goal':'reduce damage from early breakout failures by starting smaller and restoring the full 50% position only after early continuation is observed','fixed':{'base_entry':'frozen v2 DLP','target':TARGET,'stop':STOP,'horizon':HORIZON,'max_positions':SLOTS,'max_full_size_per_idea':0.50,'friction_round_trip':FRICTION,'ranking':'v3.2 liquidity'},'protocol':{'validation_2023':VAL1,'validation_2024':VAL2,'final_research_period':FINAL,'final_not_used_for_selection':True,'min_wealth_ratio_each_validation':MIN_WEALTH_RATIO,'min_dd_reduction_each_validation':MIN_DD_REDUCTION,'min_active_ge2_ratio_each_validation':MIN_ACTIVE_GE2_RATIO},'dataset':{'stocks':len(data),'signals':len(signals)},'baseline_v32':{'2023':slim(b23),'2024':slim(b24),'final':slim(bf)},'grid':{'probe_fracs':PROBE_FRACS,'add_days':ADD_DAYS,'confirm_modes':CONFIRM_MODES,'unconfirmed_actions':UNCONFIRMED_ACTIONS,'tested':tested,'eligible':len(eligible)},'selected':best,'final_result':slim(fin) if fin else None,'top20':eligible[:20],'best_near_misses':allrows[:20]}
    if fin:
        result['comparison_final']={'wealth_ratio':(1+fin['total_return'])/(1+bf['total_return']),'drawdown_reduction':1-abs(fin['max_drawdown'])/abs(bf['max_drawdown']),'return_change_pp':100*(fin['total_return']-bf['total_return']),'dd_change_pp':100*(abs(bf['max_drawdown'])-abs(fin['max_drawdown'])),'active_ge2_rate_ratio':fin['weekly']['active_ge_2_rate']/bf['weekly']['active_ge_2_rate'] if bf['weekly']['active_ge_2_rate'] else None}
    with open('tmp/egx_backtest/results_v57_staged_probe_addon.json','w',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'pattern':result['pattern'],'grid':result['grid'],'baseline_v32':result['baseline_v32'],'selected':result['selected'],'final_result':result['final_result'],'comparison_final':result.get('comparison_final'),'best_near_misses':result['best_near_misses'][:5]},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
