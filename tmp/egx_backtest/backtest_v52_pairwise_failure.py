import glob,json,math,os,sys
from collections import defaultdict
from datetime import datetime,timedelta

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3
import backtest_v51_correlation_risk as v51

TRAIN=("2021-01-01","2022-12-31")
VAL1=("2023-01-01","2023-12-31")
VAL2=("2024-01-01","2024-12-31")
FINAL=("2025-01-01","2026-02-28")
INITIAL=100000.0
FRICTION=0.005
TARGET=0.12
STOP=0.045
HORIZON=7
SLOTS=2
SLOT_SIZE=0.50
PAIR_MAX_CALENDAR_GAP=12
WEEKLY_TARGET=0.02

C_VALUES=[0.1,0.5,1.0,2.0]
CLASS_WEIGHTS=[None,"balanced"]
THRESHOLDS=[0.25,0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70]
MIN_WEALTH_RATIO=0.97
MIN_DD_REDUCTION=0.10
MIN_VALIDATION_TRADES=12

LEAN_FEATURES=[
    "gap_days","same_day","corr40","down40",
    "min_quality","avg_quality","min_rs20","avg_rs20",
    "min_overhead","max_breakout_ret",
    "current_market20","current_breadth20",
    "both_negative_rs20","both_low_overhead","both_extended"
]
FULL_FEATURES=LEAN_FEATURES+[
    "corr20","down20","corr20_avail","corr40_avail",
    "quality_diff","rs20_diff","min_clv","avg_clv",
    "min_body","avg_body","min_vol_ratio","avg_vol_ratio",
    "avg_overhead","avg_breakout_ret","current_market5",
    "avg_entry_market20","market20_diff","avg_entry_breadth20","breadth20_diff"
]
FEATURE_SETS={"lean":LEAN_FEATURES,"full":FULL_FEATURES}


def in_period(d,p): return p[0] <= d <= p[1]
def days_between(a,b): return abs((datetime.fromisoformat(a).date()-datetime.fromisoformat(b).date()).days)
def week_start(s):
    d=datetime.fromisoformat(s).date(); return (d-timedelta(days=(d.weekday()+1)%7)).isoformat()


def collect(sym,rows,market):
    out=[]; nxt=60; t=60
    while t < len(rows)-HORIZON:
        if t<nxt:
            t+=1; continue
        matches=[]
        for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
            c=v3.v1_candidate(rows,t,n)
            if c: matches.append(c)
        if matches:
            c=max(matches,key=lambda x:x["base_n"])
            s=v3.make_signal(sym,rows,t,c,market)
            if s and s["v2_flag"]>0:
                q=(min(s["breakout_vol_ratio"],4.0)/4.0
                   + s["clv"]
                   + min(max(s["body"],0.0),0.06)/0.06
                   + min(max(s["rs20"]+0.10,0.0),0.30)/0.30
                   + min(max(s["nearest_overhead_pct"],0.0),0.10)/0.10
                   - min(max(s["breakout_ret"]-0.03,0.0),0.03)/0.03)
                out.append({
                    "symbol":sym,"entry_date":rows[t]["date"],"entry":rows[t]["close"],
                    "liquidity":c["median_base_value"],"quality":q,
                    "body":s["body"],"clv":s["clv"],"breakout_ret":s["breakout_ret"],
                    "breakout_vol_ratio":s["breakout_vol_ratio"],"rs20":s["rs20"],
                    "nearest_overhead":s["nearest_overhead_pct"],
                    "market5":s["market5_ret"],"market20":s["market20_ret"],
                    "breadth20":s["market_breadth20"],
                    "future":rows[t+1:t+1+HORIZON]
                })
            nxt=t+11
        t+=1
    return out


def finalize(x):
    e=x["entry"]; tgt=e*(1+TARGET); stp=e*(1-STOP); fut=x["future"]
    base={k:x[k] for k in ["symbol","entry_date","entry","liquidity","quality","body","clv","breakout_ret","breakout_vol_ratio","rs20","nearest_overhead","market5","market20","breadth20"]}
    for i,d in enumerate(fut,1):
        if d["low"]<=stp:
            return {**base,"exit_date":d["date"],"exit_price":stp,"gross_return":-STOP,"exit_type":"stop","holding":i}
        if d["high"]>=tgt:
            return {**base,"exit_date":d["date"],"exit_price":tgt,"gross_return":TARGET,"exit_type":"target","holding":i}
    d=fut[-1]
    return {**base,"exit_date":d["date"],"exit_price":d["close"],"gross_return":d["close"]/e-1,"exit_type":"timeout","holding":HORIZON}


def build_maps(data):
    closes={}; retmaps={}; dates=set()
    for sym,rows in data.items():
        cm={}; rm={}
        for i,r in enumerate(rows):
            cm[r["date"]]=r["close"]; dates.add(r["date"])
            if i>0 and rows[i-1]["close"]>0:
                rr=r["close"]/rows[i-1]["close"]-1
                if -0.35<=rr<=0.35: rm[r["date"]]=rr
        closes[sym]=cm; retmaps[sym]=rm
    return closes,retmaps,sorted(dates)


def pearson(a,b):
    if len(a)<3:return None
    ma=sum(a)/len(a); mb=sum(b)/len(b)
    va=sum((x-ma)**2 for x in a); vb=sum((x-mb)**2 for x in b)
    if va<=1e-12 or vb<=1e-12:return 0.0
    return sum((a[i]-ma)*(b[i]-mb) for i in range(len(a)))/math.sqrt(va*vb)


def pair_history(a,b,date,lookback,retmaps):
    ra=retmaps.get(a,{}); rb=retmaps.get(b,{})
    ds=sorted(set(ra).intersection(rb)); ds=[d for d in ds if d<date][-lookback:]
    min_n=max(10,lookback//2)
    if len(ds)<min_n:return {"n":len(ds),"corr":0.0,"down":0.0,"avail":0.0}
    xa=[ra[d] for d in ds]; xb=[rb[d] for d in ds]
    corr=pearson(xa,xb)
    stress=[i for i in range(len(ds)) if xa[i]<=-0.01 or xb[i]<=-0.01]
    joint=sum(1 for i in stress if xa[i]<=-0.01 and xb[i]<=-0.01)
    return {"n":len(ds),"corr":0.0 if corr is None else corr,"down":joint/len(stress) if stress else 0.0,"avail":1.0}


def pair_features(a,b,retmaps):
    # Symmetric signal features, with market state taken at the later entry date.
    later=a if a["entry_date"]>=b["entry_date"] else b
    h20=pair_history(a["symbol"],b["symbol"],later["entry_date"],20,retmaps)
    h40=pair_history(a["symbol"],b["symbol"],later["entry_date"],40,retmaps)
    qa,qb=a["quality"],b["quality"]; ra,rb=a["rs20"],b["rs20"]
    oa,ob=a["nearest_overhead"],b["nearest_overhead"]
    ba,bb=a["body"],b["body"]; ca,cb=a["clv"],b["clv"]
    va,vb=a["breakout_vol_ratio"],b["breakout_vol_ratio"]
    bra,brb=a["breakout_ret"],b["breakout_ret"]
    ma,mb=a["market20"],b["market20"]; bwa,bwb=a["breadth20"],b["breadth20"]
    return {
        "gap_days":float(days_between(a["entry_date"],b["entry_date"])),
        "same_day":1.0 if a["entry_date"]==b["entry_date"] else 0.0,
        "corr20":h20["corr"],"down20":h20["down"],"corr20_avail":h20["avail"],
        "corr40":h40["corr"],"down40":h40["down"],"corr40_avail":h40["avail"],
        "min_quality":min(qa,qb),"avg_quality":(qa+qb)/2,"quality_diff":abs(qa-qb),
        "min_rs20":min(ra,rb),"avg_rs20":(ra+rb)/2,"rs20_diff":abs(ra-rb),
        "min_clv":min(ca,cb),"avg_clv":(ca+cb)/2,
        "min_body":min(ba,bb),"avg_body":(ba+bb)/2,
        "min_vol_ratio":min(va,vb),"avg_vol_ratio":(va+vb)/2,
        "min_overhead":min(oa,ob),"avg_overhead":(oa+ob)/2,
        "max_breakout_ret":max(bra,brb),"avg_breakout_ret":(bra+brb)/2,
        "current_market5":later["market5"],"current_market20":later["market20"],"current_breadth20":later["breadth20"],
        "avg_entry_market20":(ma+mb)/2,"market20_diff":abs(ma-mb),
        "avg_entry_breadth20":(bwa+bwb)/2,"breadth20_diff":abs(bwa-bwb),
        "both_negative_rs20":1.0 if ra<0 and rb<0 else 0.0,
        "both_low_overhead":1.0 if oa<0.02 and ob<0.02 else 0.0,
        "both_extended":1.0 if bra>0.04 and brb>0.04 else 0.0,
    }


def build_pair_samples(trades,retmaps,period):
    arr=sorted([x for x in trades if in_period(x["entry_date"],period)],key=lambda x:(x["entry_date"],x["symbol"]))
    out=[]
    for i,a in enumerate(arr):
        for j in range(i+1,len(arr)):
            b=arr[j]; gap=days_between(a["entry_date"],b["entry_date"])
            if gap>PAIR_MAX_CALENDAR_GAP and b["entry_date"]>a["entry_date"]: break
            if gap>PAIR_MAX_CALENDAR_GAP: continue
            f=pair_features(a,b,retmaps)
            y=1 if a["gross_return"]<0 and b["gross_return"]<0 else 0
            out.append({"features":f,"label":y,"a":a["symbol"],"b":b["symbol"],"date":max(a["entry_date"],b["entry_date"]),"both_stop":a["exit_type"]=="stop" and b["exit_type"]=="stop"})
    return out


def matrix(samples,names):
    X=np.array([[s["features"].get(n,0.0) for n in names] for s in samples],dtype=float)
    y=np.array([s["label"] for s in samples],dtype=int)
    return X,y


def make_model(c,class_weight):
    return Pipeline([("scale",StandardScaler()),("logit",LogisticRegression(C=c,class_weight=class_weight,max_iter=5000,solver="liblinear",random_state=42))])


def model_diag(model,samples,names):
    if not samples:return {"pairs":0,"positive_pairs":0,"positive_rate":0,"auc":None,"avg_prob_positive":None,"avg_prob_other":None}
    X,y=matrix(samples,names); p=model.predict_proba(X)[:,1]
    auc=roc_auc_score(y,p) if len(set(y.tolist()))>1 else None
    pos=p[y==1]; neg=p[y==0]
    return {"pairs":len(y),"positive_pairs":int(y.sum()),"positive_rate":float(y.mean()),"auc":None if auc is None else float(auc),"avg_prob_positive":float(pos.mean()) if len(pos) else None,"avg_prob_other":float(neg.mean()) if len(neg) else None}


def weekly(curve):
    by=defaultdict(list)
    for r in curve:by[week_start(r["date"])].append(r)
    prev=INITIAL; vals=[]; active=[]; hit=0
    for wk in sorted(by):
        a=by[wk]; end=a[-1]["equity"]; ret=end/prev-1 if prev>0 else 0
        vals.append(ret)
        if any(x["exposure"]>1e-9 for x in a):active.append(ret)
        hit+=max(x["equity"] for x in a)/prev-1>=WEEKLY_TARGET if prev>0 else 0
        prev=end
    av=lambda x:sum(x)/len(x) if x else 0
    return {"weeks":len(vals),"avg":av(vals),"positive_rate":sum(x>0 for x in vals)/len(vals) if vals else 0,"weekend_ge_2_rate":sum(x>=WEEKLY_TARGET for x in vals)/len(vals) if vals else 0,"hit_2_anytime_rate":hit/len(vals) if vals else 0,"active_weeks":len(active),"active_avg":av(active),"active_positive_rate":sum(x>0 for x in active)/len(active) if active else 0,"active_ge_2_rate":sum(x>=WEEKLY_TARGET for x in active)/len(active) if active else 0,"worst":min(vals) if vals else 0,"best":max(vals) if vals else 0}


def maxdd(curve):return v51.maxdd(curve)


def score_pair(model,names,a,b,retmaps):
    f=pair_features(a,b,retmaps); X=np.array([[f.get(n,0.0) for n in names]],dtype=float)
    return float(model.predict_proba(X)[0,1]),f


def simulate(trades,closes,retmaps,dates,p,model=None,names=None,threshold=None):
    eb=defaultdict(list);xb=defaultdict(list)
    for t in trades:eb[t["entry_date"]].append(t);xb[t["exit_date"]].append(t)
    for d in eb:eb[d].sort(key=lambda x:(-x["liquidity"],x["symbol"]))
    ds=[d for d in dates if p[0]<=d<=p[1]];half=FRICTION/2;cash=INITIAL;pos={};last={};curve=[];real=[];skip=defaultdict(int);gates=[]
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
            q=pos.pop(s);proceeds=q["shares"]*tr["exit_price"]*(1-half);cash+=proceeds;net=proceeds/q["budget"]-1
            real.append({"symbol":s,"entry_date":q["signal"]["entry_date"],"exit_date":d,"net_return":net,"exit_type":tr["exit_type"],"holding":tr["holding"]})
        for tr in eb.get(d,[]):
            if tr["symbol"] in pos:skip["duplicate_symbol"]+=1;continue
            if len(pos)>=SLOTS:skip["max_positions"]+=1;continue
            if model is not None and pos:
                worst_prob=-1;worst_sym=None;worst_feat=None
                for osym,q in pos.items():
                    prob,feat=score_pair(model,names,tr,q["signal"],retmaps)
                    if prob>worst_prob:worst_prob=prob;worst_sym=osym;worst_feat=feat
                if worst_prob>=threshold:
                    skip["pair_failure_gate"]+=1;gates.append({"date":d,"candidate":tr["symbol"],"open_symbol":worst_sym,"failure_probability":worst_prob,"features":worst_feat});continue
            eq,_=mark(d);budget=min(eq*SLOT_SIZE,cash)
            if budget<=1:skip["cash"]+=1;continue
            invested=budget*(1-half);shares=invested/tr["entry"];cash-=budget
            pos[tr["symbol"]]={"shares":shares,"entry":tr["entry"],"budget":budget,"signal":tr};last[tr["symbol"]]=tr["entry"]
        eq,pv=mark(d);curve.append({"date":d,"equity":eq,"exposure":pv/eq if eq else 0,"open":len(pos)})
    m,pd,td=maxdd(curve);final=curve[-1]["equity"];d0=datetime.fromisoformat(curve[0]["date"]).date();d1=datetime.fromisoformat(curve[-1]["date"]).date();yrs=max((d1-d0).days/365.25,1/365.25);rs=[x["net_return"] for x in real]
    return {"trades":len(real),"skipped":sum(skip.values()),"skip_reasons":dict(skip),"final_equity":final,"total_return":final/INITIAL-1,"cagr":(final/INITIAL)**(1/yrs)-1,"max_drawdown":m,"dd_peak":pd,"dd_trough":td,"avg_trade_return":sum(rs)/len(rs) if rs else 0,"positive_trade_rate":sum(x>0 for x in rs)/len(rs) if rs else 0,"weekly":weekly(curve),"avg_exposure":sum(x["exposure"] for x in curve)/len(curve),"realized":real,"gates":gates,"curve":curve}


def slim(x):return {k:v for k,v in x.items() if k not in {"realized","gates","curve"}}


def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw");files=sorted(glob.glob(os.path.join(root,"*","*.csv")));data={}
    for fp in files:
        s=os.path.basename(fp).split(".")[0].upper();r=v3.load_csv_all(fp)
        if len(r)>=100:data[s]=r
    market=v3.build_market_maps(data);raw=[]
    for s,r in data.items():raw+=collect(s,r,market)
    trades=[finalize(x) for x in raw];closes,retmaps,dates=build_maps(data)
    train_pairs=build_pair_samples(trades,retmaps,TRAIN);v23_pairs=build_pair_samples(trades,retmaps,VAL1);v24_pairs=build_pair_samples(trades,retmaps,VAL2);final_pairs=build_pair_samples(trades,retmaps,FINAL)
    if len(train_pairs)<20 or sum(x["label"] for x in train_pairs)<3 or sum(1-x["label"] for x in train_pairs)<3:
        raise RuntimeError(f"Insufficient pair training sample: n={len(train_pairs)}, positives={sum(x['label'] for x in train_pairs)}")
    def tp(p):return [x for x in trades if in_period(x["entry_date"],p) and x["exit_date"]<=p[1]]
    b23=simulate(tp(VAL1),closes,retmaps,dates,VAL1);b24=simulate(tp(VAL2),closes,retmaps,dates,VAL2);bf=simulate(tp(FINAL),closes,retmaps,dates,FINAL)
    candidates=[];near=[];models_meta=[]
    fitted={}
    for fs_name,names in FEATURE_SETS.items():
      Xtr,ytr=matrix(train_pairs,names)
      for c in C_VALUES:
       for cw in CLASS_WEIGHTS:
        key=f"{fs_name}_C{c}_cw{cw or 'none'}";model=make_model(c,cw);model.fit(Xtr,ytr);fitted[key]=(model,names)
        diag={"key":key,"feature_set":fs_name,"C":c,"class_weight":cw,"train":model_diag(model,train_pairs,names),"2023_pairs":model_diag(model,v23_pairs,names),"2024_pairs":model_diag(model,v24_pairs,names)};models_meta.append(diag)
        for th in THRESHOLDS:
            a=simulate(tp(VAL1),closes,retmaps,dates,VAL1,model,names,th);b=simulate(tp(VAL2),closes,retmaps,dates,VAL2,model,names,th)
            if a["trades"]<MIN_VALIDATION_TRADES or b["trades"]<MIN_VALIDATION_TRADES:continue
            wr1=(1+a["total_return"])/(1+b23["total_return"]);wr2=(1+b["total_return"])/(1+b24["total_return"])
            dr1=1-abs(a["max_drawdown"])/abs(b23["max_drawdown"]);dr2=1-abs(b["max_drawdown"])/abs(b24["max_drawdown"])
            row={"model_key":key,"threshold":th,"2023":slim(a),"2024":slim(b),"min_wealth_ratio":min(wr1,wr2),"min_dd_reduction":min(dr1,dr2),"min_cagr":min(a["cagr"],b["cagr"]),"min_active_week_avg":min(a["weekly"]["active_avg"],b["weekly"]["active_avg"])}
            near.append(row)
            if row["min_wealth_ratio"]>=MIN_WEALTH_RATIO and row["min_dd_reduction"]>=MIN_DD_REDUCTION:candidates.append(row)
    candidates.sort(key=lambda x:(x["min_dd_reduction"],x["min_wealth_ratio"],x["min_cagr"],x["min_active_week_avg"]),reverse=True)
    near.sort(key=lambda x:(x["min_wealth_ratio"]+x["min_dd_reduction"],x["min_cagr"]),reverse=True)
    best=candidates[0] if candidates else None;fin=None;final_diag=None;coef=None
    if best:
        model,names=fitted[best["model_key"]];fin=simulate(tp(FINAL),closes,retmaps,dates,FINAL,model,names,best["threshold"]);final_diag=model_diag(model,final_pairs,names)
        lr=model.named_steps["logit"];coef=sorted([{"feature":n,"coefficient":float(v)} for n,v in zip(names,lr.coef_[0])],key=lambda x:abs(x["coefficient"]),reverse=True)
    result={
        "pattern":"Defensive Lift v5.2 Pairwise Failure Probability",
        "goal":"predict shared failure risk from contemporaneous pair features and block only high-risk second positions while keeping v3.2 50% slot size",
        "fixed":{"entry":"frozen v2 DLP","target":TARGET,"stop":STOP,"horizon":HORIZON,"slots":SLOTS,"slot_size":SLOT_SIZE,"friction_round_trip":FRICTION,"ranking":"frozen v3.2 liquidity ranking"},
        "protocol":{"model_train":TRAIN,"validation_2023":VAL1,"validation_2024":VAL2,"final_holdout":FINAL,"final_not_used_for_model_or_threshold_selection":True,"pair_window_calendar_days":PAIR_MAX_CALENDAR_GAP,"label":"both trades gross return < 0","min_wealth_ratio_vs_v32_each_validation":MIN_WEALTH_RATIO,"min_drawdown_reduction_each_validation":MIN_DD_REDUCTION},
        "dataset":{"stocks":len(data),"signals":len(trades),"train_pairs":len(train_pairs),"train_positive_pairs":sum(x["label"] for x in train_pairs),"2023_pairs":len(v23_pairs),"2024_pairs":len(v24_pairs),"final_pairs":len(final_pairs)},
        "baseline_v32":{"2023":slim(b23),"2024":slim(b24),"final":slim(bf)},
        "grid":{"models":len(models_meta),"thresholds":THRESHOLDS,"tested_portfolio_configs":len(near),"eligible":len(candidates),"model_diagnostics":models_meta},
        "selected":best,"final_result":slim(fin) if fin else None,"final_pair_model_diagnostic":final_diag,"selected_model_coefficients":coef,"best_near_misses":near[:20]
    }
    if fin:
        result["final_gate_diagnostics"]={"blocked_entries":fin["skip_reasons"].get("pair_failure_gate",0),"examples":fin["gates"][:100]}
        result["comparison_final"]={"wealth_ratio":(1+fin["total_return"])/(1+bf["total_return"]),"drawdown_reduction":1-abs(fin["max_drawdown"])/abs(bf["max_drawdown"]),"return_change_pp":100*(fin["total_return"]-bf["total_return"]),"dd_improvement_pp":100*(abs(bf["max_drawdown"])-abs(fin["max_drawdown"])),"active_week_avg_change_pp":100*(fin["weekly"]["active_avg"]-bf["weekly"]["active_avg"]),"active_ge2_rate_change_pp":100*(fin["weekly"]["active_ge_2_rate"]-bf["weekly"]["active_ge_2_rate"])}
    with open("tmp/egx_backtest/results_v52_pairwise_failure.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result.get(k) for k in ["pattern","protocol","dataset","baseline_v32","grid","selected","final_result","final_pair_model_diagnostic","selected_model_coefficients","comparison_final"]},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
