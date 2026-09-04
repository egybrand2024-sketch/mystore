import glob,json,math,os,sys
from collections import defaultdict
from datetime import datetime,timedelta
sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3
import backtest_v42_regime_adaptive as v42

VAL1=v42.VAL1; VAL2=v42.VAL2; FINAL=v42.FINAL
INITIAL=v42.INITIAL; FRICTION=v42.FRICTION
TARGET=0.12; STOP=0.045; HORIZON=7; SLOTS=2
WEEKLY_TARGET=0.02

LOOKBACKS=[20,40,60]
CORR_THRESH=[0.20,0.35,0.50,0.65,0.80]
DOWN_THRESH=[0.25,0.40,0.55,1.01]
GATE_MODES=["corr","or","and"]
RANK_MODES=["liquidity","quality"]
MIN_WEALTH_RATIO=0.97
MIN_DD_REDUCTION=0.10
MIN_TRADES=12


def in_period(d,p): return p[0] <= d <= p[1]
def week_start(s):
    d=datetime.fromisoformat(s).date(); return (d-timedelta(days=(d.weekday()+1)%7)).isoformat()

def collect(sym,rows,market):
    out=[]; nxt=60; t=60
    while t < len(rows)-HORIZON:
        if t<nxt: t+=1; continue
        ms=[]
        for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
            c=v3.v1_candidate(rows,t,n)
            if c: ms.append(c)
        if ms:
            c=max(ms,key=lambda x:x["base_n"]); s=v3.make_signal(sym,rows,t,c,market)
            if s and s["v2_flag"]>0:
                # Fixed, non-fitted quality score used only to rank simultaneous candidates.
                q=(min(s["breakout_vol_ratio"],4.0)/4.0
                   + s["clv"]
                   + min(max(s["body"],0.0),0.06)/0.06
                   + min(max(s["rs20"]+0.10,0.0),0.30)/0.30
                   + min(max(s["nearest_overhead_pct"],0.0),0.10)/0.10
                   - min(max(s["breakout_ret"]-0.03,0.0),0.03)/0.03)
                out.append({
                    "symbol":sym,"entry_date":rows[t]["date"],"entry":rows[t]["close"],
                    "liquidity":c["median_base_value"],"quality":q,
                    "breakout_vol_ratio":s["breakout_vol_ratio"],"clv":s["clv"],"body":s["body"],
                    "rs20":s["rs20"],"nearest_overhead":s["nearest_overhead_pct"],
                    "future":rows[t+1:t+1+HORIZON]
                })
            nxt=t+11
        t+=1
    return out

def finalize(x):
    e=x["entry"]; tgt=e*(1+TARGET); stp=e*(1-STOP); f=x["future"]
    for i,d in enumerate(f,1):
        if d["low"]<=stp:
            return {**{k:x[k] for k in ["symbol","entry_date","entry","liquidity","quality"]},"exit_date":d["date"],"exit_price":stp,"gross_return":-STOP,"exit_type":"stop","holding":i}
        if d["high"]>=tgt:
            return {**{k:x[k] for k in ["symbol","entry_date","entry","liquidity","quality"]},"exit_date":d["date"],"exit_price":tgt,"gross_return":TARGET,"exit_type":"target","holding":i}
    d=f[-1]
    return {**{k:x[k] for k in ["symbol","entry_date","entry","liquidity","quality"]},"exit_date":d["date"],"exit_price":d["close"],"gross_return":d["close"]/e-1,"exit_type":"timeout","holding":HORIZON}

def build_maps(data):
    closes={}; returns={}; dates=set()
    for s,rows in data.items():
        cm={}; rm={}
        for i,r in enumerate(rows):
            cm[r["date"]]=r["close"]; dates.add(r["date"])
            if i>0 and rows[i-1]["close"]>0:
                rr=r["close"]/rows[i-1]["close"]-1
                if -0.35<=rr<=0.35: rm[r["date"]]=rr
        closes[s]=cm; returns[s]=rm
    return closes,returns,sorted(dates)

def pearson(a,b):
    n=len(a)
    if n<3:return None
    ma=sum(a)/n; mb=sum(b)/n
    va=sum((x-ma)**2 for x in a); vb=sum((x-mb)**2 for x in b)
    if va<=1e-12 or vb<=1e-12:return 0.0
    return sum((a[i]-ma)*(b[i]-mb) for i in range(n))/math.sqrt(va*vb)

def pair_stats(a,b,date,lookback,retmaps):
    ra=retmaps.get(a,{}); rb=retmaps.get(b,{})
    ds=sorted(set(ra).intersection(rb)); ds=[d for d in ds if d<date][-lookback:]
    if len(ds)<max(12,lookback//2): return {"n":len(ds),"corr":None,"down_overlap":None}
    xa=[ra[d] for d in ds]; xb=[rb[d] for d in ds]; corr=pearson(xa,xb)
    stress=[i for i in range(len(ds)) if xa[i]<=-0.01 or xb[i]<=-0.01]
    joint=sum(1 for i in stress if xa[i]<=-0.01 and xb[i]<=-0.01)
    down=joint/len(stress) if stress else 0.0
    return {"n":len(ds),"corr":corr,"down_overlap":down}

def blocked(stats,cfg):
    if stats["corr"] is None:return False
    c=stats["corr"]>=cfg["corr_threshold"]
    d=(stats["down_overlap"] or 0)>=cfg["down_threshold"]
    if cfg["gate_mode"]=="corr":return c
    if cfg["gate_mode"]=="or":return c or d
    return c and d

def maxdd(curve): return v42.maxdd(curve)

def weekly(curve):
    by=defaultdict(list)
    for r in curve: by[week_start(r["date"])].append(r)
    prev=INITIAL; vals=[]; active=[]; hit_any=0
    for wk in sorted(by):
        arr=by[wk]; end=arr[-1]["equity"]; ret=end/prev-1 if prev>0 else 0
        vals.append(ret); is_active=any(x["exposure"]>1e-9 for x in arr)
        if is_active: active.append(ret)
        mx=max(x["equity"] for x in arr)/prev-1 if prev>0 else 0
        hit_any += mx>=WEEKLY_TARGET; prev=end
    def avg(x):return sum(x)/len(x) if x else 0
    return {
        "weeks":len(vals),"avg":avg(vals),"median":sorted(vals)[len(vals)//2] if vals else 0,
        "positive_rate":sum(x>0 for x in vals)/len(vals) if vals else 0,
        "weekend_ge_2_rate":sum(x>=WEEKLY_TARGET for x in vals)/len(vals) if vals else 0,
        "hit_2_anytime_rate":hit_any/len(vals) if vals else 0,
        "active_weeks":len(active),"active_avg":avg(active),
        "active_positive_rate":sum(x>0 for x in active)/len(active) if active else 0,
        "active_ge_2_rate":sum(x>=WEEKLY_TARGET for x in active)/len(active) if active else 0,
        "worst":min(vals) if vals else 0,"best":max(vals) if vals else 0
    }

def sort_candidates(arr,mode):
    if mode=="quality": return sorted(arr,key=lambda x:(-x["quality"],-x["liquidity"],x["symbol"]))
    return sorted(arr,key=lambda x:(-x["liquidity"],-x["quality"],x["symbol"]))

def simulate(trades,closes,retmaps,dates,p,cfg=None):
    eb=defaultdict(list); xb=defaultdict(list)
    for t in trades: eb[t["entry_date"]].append(t); xb[t["exit_date"]].append(t)
    rank_mode="liquidity" if cfg is None else cfg["rank_mode"]
    for d in eb: eb[d]=sort_candidates(eb[d],rank_mode)
    ds=[d for d in dates if p[0]<=d<=p[1]]; half=FRICTION/2; cash=INITIAL; pos={}; last={}; curve=[]; real=[]; skip=defaultdict(int); gate_events=[]
    def mark(d):
        pv=0
        for s,q in pos.items():
            px=closes.get(s,{}).get(d)
            if px is not None:last[s]=px
            pv+=q["shares"]*last.get(s,q["entry"])
        return cash+pv,pv
    for d in ds:
        for s in list(pos):
            px=closes.get(s,{}).get(d)
            if px is not None:last[s]=px
        for tr in sorted(xb.get(d,[]),key=lambda x:x["symbol"]):
            s=tr["symbol"]
            if s not in pos:continue
            q=pos.pop(s); proceeds=q["shares"]*tr["exit_price"]*(1-half); cash+=proceeds; net=proceeds/q["budget"]-1
            real.append({"symbol":s,"entry_date":q["entry_date"],"exit_date":d,"net_return":net,"exit_type":tr["exit_type"],"holding":tr["holding"]})
        for tr in eb.get(d,[]):
            if tr["symbol"] in pos: skip["duplicate_symbol"]+=1; continue
            if len(pos)>=SLOTS: skip["max_positions"]+=1; continue
            if cfg is not None and pos:
                bad=False
                for osym in pos:
                    st=pair_stats(tr["symbol"],osym,d,cfg["lookback"],retmaps)
                    if blocked(st,cfg):
                        bad=True; gate_events.append({"date":d,"candidate":tr["symbol"],"open_symbol":osym,**st}); break
                if bad: skip["correlation_gate"]+=1; continue
            eq,_=mark(d); budget=min(eq*0.50,cash)
            if budget<=1: skip["cash"]+=1; continue
            invested=budget*(1-half); shares=invested/tr["entry"]; cash-=budget
            pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"entry_date":d,"budget":budget}; last[tr["symbol"]]=tr["entry"]
        eq,pv=mark(d); curve.append({"date":d,"equity":eq,"exposure":pv/eq if eq else 0,"open":len(pos)})
    m,pd,td=maxdd(curve); final=curve[-1]["equity"]; d0=datetime.fromisoformat(curve[0]["date"]).date(); d1=datetime.fromisoformat(curve[-1]["date"]).date(); yrs=max((d1-d0).days/365.25,1/365.25)
    rs=[x["net_return"] for x in real]
    return {"trades":len(real),"skipped":sum(skip.values()),"skip_reasons":dict(skip),"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,"max_drawdown":m,"dd_peak":pd,"dd_trough":td,"avg_trade_return":sum(rs)/len(rs) if rs else 0,"positive_trade_rate":sum(x>0 for x in rs)/len(rs) if rs else 0,"weekly":weekly(curve),"avg_exposure":sum(x["exposure"] for x in curve)/len(curve),"realized":real,"gate_events":gate_events,"curve":curve}

def overlap_diag(real,retmaps,lookback=40):
    pairs=[]
    for i in range(len(real)):
        a=real[i]
        for j in range(i+1,len(real)):
            b=real[j]
            if max(a["entry_date"],b["entry_date"])<=min(a["exit_date"],b["exit_date"]):
                later=max(a["entry_date"],b["entry_date"]); st=pair_stats(a["symbol"],b["symbol"],later,lookback,retmaps)
                pairs.append({"both_negative":a["net_return"]<0 and b["net_return"]<0,"both_stop":a["exit_type"]=="stop" and b["exit_type"]=="stop","corr":st["corr"],"down":st["down_overlap"]})
    losers=[x for x in pairs if x["both_negative"] and x["corr"] is not None]; others=[x for x in pairs if not x["both_negative"] and x["corr"] is not None]
    def av(arr,k):return sum(x[k] for x in arr if x[k] is not None)/sum(1 for x in arr if x[k] is not None) if any(x[k] is not None for x in arr) else None
    return {"overlapping_pairs":len(pairs),"both_negative_pairs":sum(x["both_negative"] for x in pairs),"both_stop_pairs":sum(x["both_stop"] for x in pairs),"avg_corr_both_negative":av(losers,"corr"),"avg_corr_other_pairs":av(others,"corr"),"avg_down_overlap_both_negative":av(losers,"down"),"avg_down_overlap_other_pairs":av(others,"down")}

def slim(x): return {k:v for k,v in x.items() if k not in {"realized","gate_events","curve"}}

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw"); files=sorted(glob.glob(os.path.join(root,"*","*.csv"))); data={}
    for fp in files:
        s=os.path.basename(fp).split(".")[0].upper(); r=v3.load_csv_all(fp)
        if len(r)>=100:data[s]=r
    market=v3.build_market_maps(data); raw=[]
    for s,r in data.items(): raw+=collect(s,r,market)
    alltr=[finalize(x) for x in raw]; closes,retmaps,dates=build_maps(data)
    def tp(p): return [x for x in alltr if in_period(x["entry_date"],p) and x["exit_date"]<=p[1]]
    b23=simulate(tp(VAL1),closes,retmaps,dates,VAL1,None); b24=simulate(tp(VAL2),closes,retmaps,dates,VAL2,None); bf=simulate(tp(FINAL),closes,retmaps,dates,FINAL,None)
    ranked=[]; tested=0
    for lb in LOOKBACKS:
      for ct in CORR_THRESH:
       for dt in DOWN_THRESH:
        for gm in GATE_MODES:
         for rm in RANK_MODES:
          tested+=1; cfg={"lookback":lb,"corr_threshold":ct,"down_threshold":dt,"gate_mode":gm,"rank_mode":rm}
          a=simulate(tp(VAL1),closes,retmaps,dates,VAL1,cfg); b=simulate(tp(VAL2),closes,retmaps,dates,VAL2,cfg)
          if a["trades"]<MIN_TRADES or b["trades"]<MIN_TRADES:continue
          wr1=(1+a["total_return"])/(1+b23["total_return"]); wr2=(1+b["total_return"])/(1+b24["total_return"])
          dr1=1-abs(a["max_drawdown"])/abs(b23["max_drawdown"]); dr2=1-abs(b["max_drawdown"])/abs(b24["max_drawdown"])
          row={"config":cfg,"2023":slim(a),"2024":slim(b),"min_wealth_ratio":min(wr1,wr2),"min_dd_reduction":min(dr1,dr2),"min_cagr":min(a["cagr"],b["cagr"]),"min_active_week_avg":min(a["weekly"]["active_avg"],b["weekly"]["active_avg"])}
          if row["min_wealth_ratio"]>=MIN_WEALTH_RATIO and row["min_dd_reduction"]>=MIN_DD_REDUCTION: ranked.append(row)
    ranked.sort(key=lambda x:(x["min_dd_reduction"],x["min_wealth_ratio"],x["min_cagr"],x["min_active_week_avg"]),reverse=True)
    best=ranked[0] if ranked else None; fin=simulate(tp(FINAL),closes,retmaps,dates,FINAL,best["config"]) if best else None
    result={"pattern":"Defensive Lift v5.1 Correlation-Aware Risk Engine","goal":"preserve 50% size for strong DLP trades while blocking only overlapping hidden risk that is historically correlated","fixed":{"entry":"frozen v2 DLP","target":TARGET,"stop":STOP,"horizon":HORIZON,"slots":SLOTS,"slot_size":0.50,"friction_round_trip":FRICTION},"protocol":{"validation_2023":VAL1,"validation_2024":VAL2,"final_holdout":FINAL,"final_not_used_for_selection":True,"min_wealth_ratio_vs_v32_each_validation":MIN_WEALTH_RATIO,"min_drawdown_reduction_each_validation":MIN_DD_REDUCTION},"dataset":{"stocks":len(data),"signals":len(alltr)},"baseline_v32":{"2023":slim(b23),"2024":slim(b24),"final":slim(bf),"loss_cluster_diagnostics":{"2023":overlap_diag(b23["realized"],retmaps),"2024":overlap_diag(b24["realized"],retmaps),"final":overlap_diag(bf["realized"],retmaps)}},"grid":{"tested":tested,"eligible":len(ranked),"lookbacks":LOOKBACKS,"corr_thresholds":CORR_THRESH,"down_thresholds":DOWN_THRESH,"gate_modes":GATE_MODES,"rank_modes":RANK_MODES},"selected":best,"final_result":slim(fin) if fin else None,"top20":ranked[:20]}
    if fin:
        result["final_gate_diagnostics"]={"blocked_correlation_entries":fin["skip_reasons"].get("correlation_gate",0),"gate_events":fin["gate_events"][:100]}
        result["comparison_final"]={"wealth_ratio":(1+fin["total_return"])/(1+bf["total_return"]),"drawdown_reduction":1-abs(fin["max_drawdown"])/abs(bf["max_drawdown"]),"return_change_pp":100*(fin["total_return"]-bf["total_return"]),"dd_change_pp":100*(abs(bf["max_drawdown"])-abs(fin["max_drawdown"])),"active_week_avg_change_pp":100*(fin["weekly"]["active_avg"]-bf["weekly"]["active_avg"]),"active_ge2_rate_change_pp":100*(fin["weekly"]["active_ge_2_rate"]-bf["weekly"]["active_ge_2_rate"])}
    with open("tmp/egx_backtest/results_v51_correlation_risk.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result.get(k) for k in ["pattern","protocol","dataset","baseline_v32","grid","selected","final_result","comparison_final"]},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
