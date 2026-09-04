import glob,json,math,os,statistics,sys
from collections import defaultdict

sys.path.insert(0,"tmp/egx_backtest")
import backtest_v3_ml as v3

TRAIN=("2021-01-01","2022-12-31")
VAL1=("2023-01-01","2023-12-31")
VAL2=("2024-01-01","2024-12-31")
FINAL=("2025-01-01","2026-02-28")
TARGET=0.12
STOP=0.045
HORIZON=7
SLOTS=2

FEATURES=[f for f in v3.FEATURES if f!="v2_flag"]
GROUPS={
    "market_context":["market_breadth20","market5_ret","market20_ret","rs5","rs20"],
    "breakout_candle":["body","clv","body_to_range","upper_wick","lower_wick","breakout_ret","gap","clearance","breakout_vol_ratio","breakout_range_pct","breakout_range_atr20","nearest_overhead_pct"],
    "base_structure":["base_n","base_range","lift","prebreak_vol_ratio","compression_ratio","base_vs_prior_atr","base_close_slope","base_low_slope","up_volume_share","resistance_touches"],
    "trend_location":["pre5_ret","pre10_ret","pre20_ret","pre60_ret","dist_20_high","dist_60_high","breakout_vs_60_high","close_vs_sma20","close_vs_sma50","slope10","max_abs_ret60","log_liquidity"],
}


def finite(x): return x is not None and isinstance(x,(int,float)) and math.isfinite(x)
def mean(a):
    a=[x for x in a if finite(x)]
    return sum(a)/len(a) if a else None
def median(a):
    a=[x for x in a if finite(x)]
    return statistics.median(a) if a else None
def quantile(a,q):
    a=sorted(x for x in a if finite(x))
    if not a:return None
    if len(a)==1:return a[0]
    p=(len(a)-1)*q; lo=int(math.floor(p)); hi=int(math.ceil(p))
    if lo==hi:return a[lo]
    w=p-lo
    return a[lo]*(1-w)+a[hi]*w

def auc(vals,labels):
    pairs=[(float(v),int(y)) for v,y in zip(vals,labels) if finite(v)]
    pos=[v for v,y in pairs if y==1]; neg=[v for v,y in pairs if y==0]
    if not pos or not neg:return None
    wins=0.0
    for p in pos:
        for n in neg:
            if p>n:wins+=1
            elif p==n:wins+=0.5
    return wins/(len(pos)*len(neg))

def pooled_effect(a,b):
    a=[x for x in a if finite(x)]; b=[x for x in b if finite(x)]
    if len(a)<2 or len(b)<2:return None
    va=statistics.pvariance(a); vb=statistics.pvariance(b)
    sd=math.sqrt((va+vb)/2)
    return (mean(a)-mean(b))/sd if sd>1e-12 else 0.0

def in_period(d,p): return p[0]<=d<=p[1]

def collect_rich(sym,rows,market):
    out=[]; nxt=60; t=60
    while t < len(rows)-HORIZON:
        if t<nxt:
            t+=1; continue
        matches=[]
        for n in range(v3.MIN_BASE,v3.MAX_BASE+1):
            c=v3.v1_candidate(rows,t,n)
            if c:matches.append(c)
        if matches:
            c=max(matches,key=lambda x:x["base_n"])
            s=v3.make_signal(sym,rows,t,c,market)
            if s and s["v2_flag"]>0:
                rec={k:s.get(k) for k in FEATURES}
                rec.update({"symbol":sym,"entry_i":t,"entry_date":rows[t]["date"],"entry":rows[t]["close"],"liquidity":c["median_base_value"],"resistance":c["base_high"]})
                out.append(rec)
            nxt=t+11
        t+=1
    return out

def outcome_v32(rows,s):
    e=s["entry"]; tgt=e*(1+TARGET); stp=e*(1-STOP)
    fut=rows[s["entry_i"]+1:s["entry_i"]+1+HORIZON]
    if len(fut)<HORIZON:return None
    max_before=0.0; min_before=0.0
    for h,d in enumerate(fut,1):
        max_before=max(max_before,d["high"]/e-1)
        min_before=min(min_before,d["low"]/e-1)
        if d["low"]<=stp:
            return {"exit_date":d["date"],"exit_type":"stop","holding":h,"gross_return":-STOP,"mfe_before_exit":max_before,"mae_before_exit":min_before}
        if d["high"]>=tgt:
            return {"exit_date":d["date"],"exit_type":"target","holding":h,"gross_return":TARGET,"mfe_before_exit":max_before,"mae_before_exit":min_before}
    d=fut[-1]
    return {"exit_date":d["date"],"exit_type":"timeout","holding":HORIZON,"gross_return":d["close"]/e-1,"mfe_before_exit":max_before,"mae_before_exit":min_before}

def build(data):
    market=v3.build_market_maps(data); sigs=[]
    for sym,rows in data.items():sigs+=collect_rich(sym,rows,market)
    out=[]
    for s in sigs:
        o=outcome_v32(data[s["symbol"]],s)
        if o:out.append({**s,**o})
    return out

def accepted_portfolio(trades,p):
    arr=[t for t in trades if in_period(t["entry_date"],p) and t["exit_date"]<=p[1]]
    by=defaultdict(list)
    for t in arr:by[t["entry_date"]].append(t)
    dates=sorted(set([t["entry_date"] for t in arr]+[t["exit_date"] for t in arr]))
    pos={}; accepted=[]; skipped=[]
    for d in dates:
        for s in list(pos):
            if pos[s]["exit_date"]==d:pos.pop(s)
        for t in sorted(by.get(d,[]),key=lambda x:(-x["liquidity"],x["symbol"])):
            if t["symbol"] in pos:
                skipped.append({"symbol":t["symbol"],"entry_date":d,"reason":"duplicate"});continue
            if len(pos)>=SLOTS:
                skipped.append({"symbol":t["symbol"],"entry_date":d,"reason":"max_positions"});continue
            pos[t["symbol"]]=t; accepted.append(t)
    return accepted,skipped

def labels_summary(arr):
    return {
        "n":len(arr),
        "targets":sum(t["exit_type"]=="target" for t in arr),
        "stops":sum(t["exit_type"]=="stop" for t in arr),
        "timeouts":sum(t["exit_type"]=="timeout" for t in arr),
        "day1_stops":sum(t["exit_type"]=="stop" and t["holding"]==1 for t in arr),
        "fast_stops_2d":sum(t["exit_type"]=="stop" and t["holding"]<=2 for t in arr),
        "fast_stops_3d":sum(t["exit_type"]=="stop" and t["holding"]<=3 for t in arr),
        "fast_stop_2d_rate":sum(t["exit_type"]=="stop" and t["holding"]<=2 for t in arr)/len(arr) if arr else 0,
        "stop_holding_days":[t["holding"] for t in arr if t["exit_type"]=="stop"],
    }

def feature_stats(arr,feature,label_fn):
    good=[t for t in arr if finite(t.get(feature))]
    y=[1 if label_fn(t) else 0 for t in good]; vals=[t[feature] for t in good]
    fast=[v for v,z in zip(vals,y) if z]; other=[v for v,z in zip(vals,y) if not z]
    a=auc(vals,y)
    if a is None:return None
    return {
        "n":len(good),"n_fast":sum(y),
        "mean_fast":mean(fast),"mean_other":mean(other),
        "median_fast":median(fast),"median_other":median(other),
        "effect_fast_minus_other":pooled_effect(fast,other),
        "auc_high_predicts_fast":a,
        "direction":"high" if a>=0.5 else "low",
        "oriented_auc":max(a,1-a),
    }

def cross_year_features(a23,a24):
    rows=[]
    lab=lambda t:t["exit_type"]=="stop" and t["holding"]<=2
    for f in FEATURES:
        s23=feature_stats(a23,f,lab); s24=feature_stats(a24,f,lab)
        if not s23 or not s24:continue
        same=s23["direction"]==s24["direction"]
        rows.append({
            "feature":f,"2023":s23,"2024":s24,"same_direction":same,
            "min_oriented_auc":min(s23["oriented_auc"],s24["oriented_auc"]),
            "avg_oriented_auc":mean([s23["oriented_auc"],s24["oriented_auc"]]),
            "min_abs_effect":min(abs(s23["effect_fast_minus_other"] or 0),abs(s24["effect_fast_minus_other"] or 0)),
        })
    rows.sort(key=lambda x:(x["same_direction"],x["min_oriented_auc"],x["min_abs_effect"]),reverse=True)
    return rows

def threshold_flag_stats(arr,feature,side,threshold):
    lab=lambda t:t["exit_type"]=="stop" and t["holding"]<=2
    eligible=[t for t in arr if finite(t.get(feature))]
    if side=="low": flagged=[t for t in eligible if t[feature]<=threshold]
    else: flagged=[t for t in eligible if t[feature]>=threshold]
    base=sum(lab(t) for t in eligible)/len(eligible) if eligible else 0
    fr=sum(lab(t) for t in flagged)/len(flagged) if flagged else 0
    return {
        "n":len(flagged),"coverage":len(flagged)/len(eligible) if eligible else 0,
        "fast_stop_rate":fr,"base_fast_stop_rate":base,
        "enrichment":fr/base if base>0 else None,
        "target_rate":sum(t["exit_type"]=="target" for t in flagged)/len(flagged) if flagged else 0,
        "stop_rate":sum(t["exit_type"]=="stop" for t in flagged)/len(flagged) if flagged else 0,
    }

def training_quantile_flags(train,a23,a24):
    rows=[]
    for f in FEATURES:
        vals=[t.get(f) for t in train if finite(t.get(f))]
        if len(vals)<10:continue
        q25=quantile(vals,0.25); q75=quantile(vals,0.75)
        for side,thr in [("low",q25),("high",q75)]:
            s23=threshold_flag_stats(a23,f,side,thr); s24=threshold_flag_stats(a24,f,side,thr)
            en=[x["enrichment"] for x in [s23,s24] if x["enrichment"] is not None]
            rows.append({
                "feature":f,"side":side,"threshold_from_2021_22":thr,
                "2023":s23,"2024":s24,
                "min_enrichment":min(en) if len(en)==2 else None,
                "max_coverage":max(s23["coverage"],s24["coverage"]),
                "min_n":min(s23["n"],s24["n"]),
            })
    rows.sort(key=lambda x:((x["min_enrichment"] or -1),x["min_n"],-x["max_coverage"]),reverse=True)
    return rows

def eval_pair(arr,a,b):
    def hit(t,flag):
        v=t.get(flag["feature"])
        if not finite(v):return False
        return v<=flag["threshold_from_2021_22"] if flag["side"]=="low" else v>=flag["threshold_from_2021_22"]
    flagged=[t for t in arr if hit(t,a) and hit(t,b)]
    base=sum(t["exit_type"]=="stop" and t["holding"]<=2 for t in arr)/len(arr) if arr else 0
    fr=sum(t["exit_type"]=="stop" and t["holding"]<=2 for t in flagged)/len(flagged) if flagged else 0
    return {
        "n":len(flagged),"coverage":len(flagged)/len(arr) if arr else 0,
        "fast_stop_rate":fr,"base_fast_stop_rate":base,"enrichment":fr/base if base>0 else None,
        "target_rate":sum(t["exit_type"]=="target" for t in flagged)/len(flagged) if flagged else 0,
    }

def pair_flags(single,a23,a24):
    # Only combine a small stable shortlist; this is diagnostic, not a fitted strategy.
    shortlist=[x for x in single if x["min_enrichment"] is not None and x["min_enrichment"]>=1.0 and x["min_n"]>=2][:10]
    out=[]
    for i in range(len(shortlist)):
        for j in range(i+1,len(shortlist)):
            a=shortlist[i]; b=shortlist[j]
            if a["feature"]==b["feature"]:continue
            s23=eval_pair(a23,a,b); s24=eval_pair(a24,a,b)
            ens=[s23["enrichment"],s24["enrichment"]]
            if None in ens:continue
            out.append({
                "a":{"feature":a["feature"],"side":a["side"],"threshold":a["threshold_from_2021_22"]},
                "b":{"feature":b["feature"],"side":b["side"],"threshold":b["threshold_from_2021_22"]},
                "2023":s23,"2024":s24,"min_enrichment":min(ens),"min_n":min(s23["n"],s24["n"]),"max_coverage":max(s23["coverage"],s24["coverage"]),
            })
    out.sort(key=lambda x:(x["min_enrichment"],x["min_n"],-x["max_coverage"]),reverse=True)
    return out

def group_summary(cross):
    by={}
    for g,fs in GROUPS.items():
        arr=[x for x in cross if x["feature"] in fs]
        stable=[x for x in arr if x["same_direction"]]
        stable.sort(key=lambda x:x["min_oriented_auc"],reverse=True)
        by[g]={
            "features_tested":len(arr),"stable_direction_count":len(stable),
            "best":stable[:5],
            "avg_min_oriented_auc_stable":mean([x["min_oriented_auc"] for x in stable]) if stable else None,
        }
    return by

def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw"); data={}
    for fp in sorted(glob.glob(os.path.join(root,"*","*.csv"))):
        sym=os.path.basename(fp).split(".")[0].upper(); rows=v3.load_csv_all(fp)
        if len(rows)>=100:data[sym]=rows
    trades=build(data)
    train_raw=[t for t in trades if in_period(t["entry_date"],TRAIN)]
    raw23=[t for t in trades if in_period(t["entry_date"],VAL1)]
    raw24=[t for t in trades if in_period(t["entry_date"],VAL2)]
    a23,sk23=accepted_portfolio(trades,VAL1); a24,sk24=accepted_portfolio(trades,VAL2)

    cross=cross_year_features(a23,a24)
    singles=training_quantile_flags(train_raw,a23,a24)
    pairs=pair_flags(singles,a23,a24)

    # Explicitly list the accepted fast failures so the diagnostic is auditable.
    fast_cases={
        "2023":[{k:t.get(k) for k in ["symbol","entry_date","exit_date","holding","market_breadth20","market20_ret","market5_ret","rs20","breakout_ret","breakout_vol_ratio","clv","body","nearest_overhead_pct","base_range","lift","compression_ratio","clearance"]} for t in a23 if t["exit_type"]=="stop" and t["holding"]<=2],
        "2024":[{k:t.get(k) for k in ["symbol","entry_date","exit_date","holding","market_breadth20","market20_ret","market5_ret","rs20","breakout_ret","breakout_vol_ratio","clv","body","nearest_overhead_pct","base_range","lift","compression_ratio","clearance"]} for t in a24 if t["exit_type"]=="stop" and t["holding"]<=2],
    }

    result={
        "diagnostic":"v5.8 Hazard Attribution — fast-stop decomposition",
        "status":"Diagnostic only; not a strategy version",
        "definition":{"fast_stop":"v3.2 stop -4.5% reached within first 2 sessions","target":TARGET,"stop":STOP,"horizon":HORIZON,"max_positions":SLOTS},
        "dataset":{"stocks":len(data),"rich_v2_dlp_trades":len(trades),"train_2021_22_raw":len(train_raw),"raw_2023":len(raw23),"raw_2024":len(raw24)},
        "portfolio_reproduction":{"2023":{"accepted":len(a23),"skipped":len(sk23),"summary":labels_summary(a23)},"2024":{"accepted":len(a24),"skipped":len(sk24),"summary":labels_summary(a24)}},
        "cross_year_univariate":cross,
        "group_attribution":group_summary(cross),
        "training_quantile_single_flags":singles,
        "training_quantile_pair_flags":pairs,
        "fast_stop_cases":fast_cases,
        "method_notes":[
            "All feature values are known by the breakout close; no post-entry variable is used for attribution.",
            "Feature directions are compared independently in 2023 and 2024; same-direction behavior is favored over one-year fit.",
            "Quartile thresholds are frozen from 2021-2022 raw DLP signals, then evaluated on accepted v3.2 trades in 2023 and 2024.",
            "Pair flags are exploratory combinations of at most 10 stable single flags; they are not a new trading rule.",
            "Final research period is intentionally not used in this diagnostic so it cannot rescue a weak 2023/2024 attribution story.",
        ],
    }
    with open("tmp/egx_backtest/results_v58_hazard_attribution.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({
        "diagnostic":result["diagnostic"],"dataset":result["dataset"],"portfolio_reproduction":result["portfolio_reproduction"],
        "top_cross_year_features":cross[:12],"group_attribution":result["group_attribution"],
        "top_single_flags":singles[:12],"top_pair_flags":pairs[:12],"fast_stop_cases":fast_cases,
    },ensure_ascii=False,indent=2))

if __name__=="__main__":main()
