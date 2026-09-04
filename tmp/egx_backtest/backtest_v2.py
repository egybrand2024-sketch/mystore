import csv, glob, json, math, os, itertools
from datetime import datetime

START = "2021-01-01"
END = "2026-02-28"
DEV_END = "2024-12-31"
HOLDOUT_START = "2025-01-01"
MIN_BASE = 5
MAX_BASE = 15
HORIZON = 10
STOP = -0.04
TARGET = 0.08
COOLDOWN = 10

# Frozen v1 candidate definition
MAX_BASE_RANGE = 0.10
LIFT_MIN = 0.03
LIFT_MAX = 0.08
VOL_MULT = 1.50


def fnum(v):
    if v is None: return None
    s = str(v).strip().replace(",", "")
    if not s or s.lower() in {"nan","none","null"}: return None
    try:
        x = float(s)
        if math.isnan(x) or math.isinf(x): return None
        return x
    except: return None


def parse_date(v):
    s = str(v).strip()
    if not s: return None
    try: return datetime.fromisoformat(s.replace("Z","+00:00")).date().isoformat()
    except: pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try: return datetime.strptime(s[:10], fmt).date().isoformat()
        except: pass
    return None


def load_csv(path):
    rows=[]
    with open(path,"r",encoding="utf-8-sig",errors="replace",newline="") as fh:
        sample=fh.read(8192); fh.seek(0)
        try: dialect=csv.Sniffer().sniff(sample,delimiters=",;\t")
        except: dialect=csv.excel
        raw=list(csv.reader(fh,dialect))
    if not raw: return rows
    header=[str(x).strip().lower() for x in raw[0]]
    has_header=any(x in header for x in ("date","open","high","low","close","volume"))
    data=raw[1:] if has_header else raw
    if has_header:
        idx={}
        for i,h in enumerate(header):
            if h in ("date","datetime","timestamp"): idx["date"]=i
            elif h=="open": idx["open"]=i
            elif h=="high": idx["high"]=i
            elif h=="low": idx["low"]=i
            elif h in ("close","price","adj close","adj_close"): idx["close"]=i
            elif h in ("volume","vol.","vol"): idx["volume"]=i
        if "date" not in idx: idx["date"]=0
        if not {"date","open","high","low","close","volume"}.issubset(idx):
            idx={"date":0,"open":1,"high":2,"low":3,"close":4,"volume":5}
    else:
        idx={"date":0,"open":1,"high":2,"low":3,"close":4,"volume":5}
    for r in data:
        try:
            d=parse_date(r[idx["date"]]); o=fnum(r[idx["open"]]); h=fnum(r[idx["high"]]); l=fnum(r[idx["low"]]); c=fnum(r[idx["close"]]); v=fnum(r[idx["volume"]])
        except: continue
        if not d or None in (o,h,l,c,v) or min(o,h,l,c)<=0 or v<0: continue
        if d<START or d>END: continue
        rows.append({"date":d,"open":o,"high":h,"low":l,"close":c,"volume":v})
    rows.sort(key=lambda x:x["date"])
    ded={r["date"]:r for r in rows}
    return [ded[d] for d in sorted(ded)]


def median(vals):
    vals=sorted(vals); n=len(vals)
    if not n: return 0.0
    m=n//2
    return vals[m] if n%2 else (vals[m-1]+vals[m])/2


def evaluate(future, entry):
    tgt=entry*(1+TARGET); stp=entry*(1+STOP)
    for d in future:
        # Conservative: if both happen in same daily bar, count stop first.
        if d["low"]<=stp: return False
        if d["high"]>=tgt: return True
    return False


def v1_candidate(rows,t,n):
    if t-n<0: return None
    base=rows[t-n:t]
    b_low=min(x["low"] for x in base); b_high=max(x["high"] for x in base)
    if b_low<=0: return None
    range_pct=(b_high-b_low)/b_low
    if range_pct>MAX_BASE_RANGE: return None
    closes=[x["close"] for x in base]
    min_close_i=min(range(len(closes)),key=lambda i:closes[i])
    if min_close_i>=len(base)-3: return None
    lift=base[-1]["close"]/b_low-1
    if not (LIFT_MIN<=lift<=LIFT_MAX): return None
    early_low=min(x["low"] for x in base[:-3]); late_low=min(x["low"] for x in base[-3:])
    if not late_low>early_low: return None
    med_vol=median([x["volume"] for x in base]); avg3=sum(x["volume"] for x in base[-3:])/3
    if med_vol<=0 or avg3<VOL_MULT*med_vol: return None
    br=rows[t]
    if br["close"]<=b_high: return None
    if br["close"]/base[-1]["close"]-1>0.25: return None
    med_value=median([x["close"]*x["volume"] for x in base])
    return {"base":base,"base_n":n,"base_low":b_low,"base_high":b_high,"range_pct":range_pct,"lift_pct":lift,"med_vol":med_vol,"avg3":avg3,"median_base_value":med_value}


def make_signal(symbol,rows,t,c):
    br=rows[t]; prev=rows[t-1]
    entry=br["close"]
    future=rows[t+1:t+1+HORIZON]
    candle_range=max(br["high"]-br["low"],1e-12)
    clv=(br["close"]-br["low"])/candle_range
    body=(br["close"]-br["open"])/br["open"]
    breakout_ret=br["close"]/prev["close"]-1
    breakout_clearance=br["close"]/c["base_high"]-1
    vol_ratio=br["volume"]/c["med_vol"] if c["med_vol"]>0 else 0
    pre20_ret=None
    if t>=20 and rows[t-20]["close"]>0:
        pre20_ret=prev["close"]/rows[t-20]["close"]-1
    # Compression: compare average true-ish daily range in last 3 base bars vs earlier base bars.
    base=c["base"]
    ranges=[(x["high"]-x["low"])/x["close"] for x in base if x["close"]>0]
    if len(ranges)>=5:
        late=sum(ranges[-3:])/3
        early=sum(ranges[:-3])/len(ranges[:-3])
        compression_ratio=late/early if early>0 else 99
    else: compression_ratio=99
    return {
        "symbol":symbol,"date":br["date"],"entry":entry,"base_n":c["base_n"],
        "base_range":c["range_pct"],"lift":c["lift_pct"],"median_base_value":c["median_base_value"],
        "body":body,"clv":clv,"breakout_ret":breakout_ret,"clearance":breakout_clearance,
        "vol_ratio":vol_ratio,"pre20_ret":pre20_ret,"compression_ratio":compression_ratio,
        "success":evaluate(future,entry),
        "max_return":max(x["high"] for x in future)/entry-1,
        "min_return":min(x["low"] for x in future)/entry-1,
    }


def collect_signals(symbol,rows):
    sigs=[]; next_allowed=MAX_BASE; t=MAX_BASE
    while t<len(rows)-HORIZON:
        if t<next_allowed: t+=1; continue
        matches=[]
        for n in range(MIN_BASE,MAX_BASE+1):
            c=v1_candidate(rows,t,n)
            if c: matches.append(c)
        if matches:
            c=max(matches,key=lambda x:x["base_n"])
            sigs.append(make_signal(symbol,rows,t,c))
            next_allowed=t+COOLDOWN+1
        t+=1
    return sigs


def passes(s,cfg):
    if s["body"] < cfg["min_body"]: return False
    if s["clv"] < cfg["min_clv"]: return False
    if s["breakout_ret"] > cfg["max_breakout_ret"]: return False
    if s["breakout_ret"] < cfg["min_breakout_ret"]: return False
    if s["vol_ratio"] < cfg["min_vol_ratio"]: return False
    if s["base_range"] > cfg["max_base_range"]: return False
    if s["clearance"] < cfg["min_clearance"]: return False
    if s["pre20_ret"] is not None and s["pre20_ret"] < cfg["min_pre20_ret"]: return False
    if s["compression_ratio"] > cfg["max_compression_ratio"]: return False
    if s["median_base_value"] < cfg["min_liquidity"]: return False
    return True


def wilson_lower(w,n,z=1.0):
    if n==0: return 0.0
    p=w/n; den=1+z*z/n
    center=p+z*z/(2*n)
    adj=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)
    return (center-adj)/den


def summary(sigs):
    n=len(sigs); w=sum(1 for s in sigs if s["success"])
    return {
        "signals":n,"wins":w,"win_rate":w/n if n else None,
        "unique_symbols":len(set(s["symbol"] for s in sigs)),
        "avg_max_return":sum(s["max_return"] for s in sigs)/n if n else None,
        "median_max_return":median([s["max_return"] for s in sigs]) if n else None,
        "avg_min_return":sum(s["min_return"] for s in sigs)/n if n else None,
    }


def generate_grid():
    # Limited, interpretable grid. All choices are selected using DEV only.
    params={
      "min_body":[0.0,0.005,0.01,0.02],
      "min_clv":[0.55,0.70,0.80],
      "max_breakout_ret":[0.06,0.10,0.15],
      "min_breakout_ret":[0.0,0.01],
      "min_vol_ratio":[1.0,1.5,2.0],
      "max_base_range":[0.06,0.08,0.10],
      "min_clearance":[0.0,0.005,0.01],
      "min_pre20_ret":[-0.10,-0.03,0.0],
      "max_compression_ratio":[0.8,1.0,1.25],
      "min_liquidity":[0,1_000_000,5_000_000],
    }
    keys=list(params)
    for vals in itertools.product(*(params[k] for k in keys)):
        yield dict(zip(keys,vals))


def main():
    root=os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw")
    files=sorted(glob.glob(os.path.join(root,"*","*.csv")))
    all_sigs=[]; tested=0
    for path in files:
        symbol=os.path.basename(path).split(".")[0].upper(); rows=load_csv(path)
        if len(rows)<MAX_BASE+HORIZON+20: continue
        tested+=1; all_sigs.extend(collect_signals(symbol,rows))

    dev=[s for s in all_sigs if s["date"]<=DEV_END]
    hold=[s for s in all_sigs if s["date"]>=HOLDOUT_START]

    # Frozen v1 same-period benchmarks.
    v1_dev=summary(dev); v1_hold=summary(hold)

    candidates=[]
    for cfg in generate_grid():
        selected=[s for s in dev if passes(s,cfg)]
        n=len(selected)
        # Avoid tiny, unstable configurations.
        if n<120 or len(set(s["symbol"] for s in selected))<35:
            continue
        w=sum(1 for s in selected if s["success"])
        wr=w/n
        score=wilson_lower(w,n,z=1.0)
        candidates.append({"config":cfg,"dev_signals":n,"dev_wins":w,"dev_win_rate":wr,"score":score,"dev_unique_symbols":len(set(s["symbol"] for s in selected))})

    candidates.sort(key=lambda x:(x["score"],x["dev_win_rate"],x["dev_signals"]),reverse=True)
    best=candidates[0]
    best_cfg=best["config"]
    v2_dev_sigs=[s for s in dev if passes(s,best_cfg)]
    v2_hold_sigs=[s for s in hold if passes(s,best_cfg)]

    # Robustness: nearby top configs are reported, but holdout is NOT used to pick the winner.
    top10=[]
    for c in candidates[:10]:
        hs=[s for s in hold if passes(s,c["config"])]
        top10.append({**c,"holdout":summary(hs)})

    # Feature diagnostics from DEV only: success rates by simple bins to explain what helped.
    diagnostics={}
    bins={
      "clv_ge_0_8":lambda s:s["clv"]>=0.8,
      "body_ge_1pct":lambda s:s["body"]>=0.01,
      "vol_ratio_ge_1_5":lambda s:s["vol_ratio"]>=1.5,
      "base_range_le_8pct":lambda s:s["base_range"]<=0.08,
      "breakout_ret_le_10pct":lambda s:s["breakout_ret"]<=0.10,
      "pre20_nonnegative":lambda s:(s["pre20_ret"] is not None and s["pre20_ret"]>=0),
      "compression_le_1":lambda s:s["compression_ratio"]<=1.0,
    }
    for name,fn in bins.items(): diagnostics[name]=summary([s for s in dev if fn(s)])

    result={
      "pattern":"Defensive Lift v2 research",
      "dataset":{"start":START,"end":END,"stocks_tested":tested,"files_found":len(files)},
      "methodology":{
        "development_period":[START,DEV_END],
        "holdout_period":[HOLDOUT_START,END],
        "selection":"v2 configuration selected ONLY on development period using 1-sigma Wilson lower bound; holdout not used for selection",
        "minimum_dev_signals":120,"minimum_dev_unique_symbols":35,
        "target":TARGET,"stop":STOP,"horizon":HORIZON,
        "same_bar_target_stop":"stop first"
      },
      "v1_benchmark":{"development":v1_dev,"holdout":v1_hold},
      "grid_configs_evaluated":len(candidates),
      "best_config":best_cfg,
      "best_dev_selection":summary(v2_dev_sigs),
      "untouched_holdout_result":summary(v2_hold_sigs),
      "improvement_vs_v1_holdout_win_rate":(summary(v2_hold_sigs)["win_rate"]-v1_hold["win_rate"]) if v2_hold_sigs and v1_hold["win_rate"] is not None else None,
      "top10_dev_configs_with_holdout_shown_after_selection":top10,
      "dev_feature_diagnostics":diagnostics,
      "v2_holdout_signals":v2_hold_sigs,
    }
    os.makedirs("tmp/egx_backtest",exist_ok=True)
    with open("tmp/egx_backtest/results_v2.json","w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ["pattern","dataset","methodology","v1_benchmark","grid_configs_evaluated","best_config","best_dev_selection","untouched_holdout_result","improvement_vs_v1_holdout_win_rate"]},indent=2))

if __name__=="__main__": main()
