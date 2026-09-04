import csv, glob, json, math, os
from datetime import datetime

START = "2021-01-01"
END = "2026-02-28"
MIN_BASE = 5
MAX_BASE = 15
MAX_BASE_RANGE = 0.10
LIFT_MIN = 0.03
LIFT_MAX = 0.08
VOL_MULT = 1.50
HORIZON = 10
STOP = -0.04
TARGETS = [0.05, 0.08, 0.10]
COOLDOWN = 10
LIQUIDITY_DAILY_VALUE = 1_000_000

def fnum(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(s)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except:
        return None

def parse_date(v):
    s = str(v).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z","+00:00")).date().isoformat()
    except:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except:
            pass
    return None

def load_csv(path):
    rows = []
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except:
            dialect = csv.excel
        reader = csv.reader(fh, dialect)
        raw = list(reader)
    if not raw:
        return rows
    header = [str(x).strip().lower() for x in raw[0]]
    has_header = any(x in header for x in ("date","open","high","low","close","volume"))
    data = raw[1:] if has_header else raw
    if has_header:
        idx = {}
        for i, h in enumerate(header):
            h2 = h.strip().lower()
            if h2 in ("date","datetime","timestamp"): idx["date"] = i
            elif h2 == "open": idx["open"] = i
            elif h2 == "high": idx["high"] = i
            elif h2 == "low": idx["low"] = i
            elif h2 in ("close","price","adj close","adj_close"): idx["close"] = i
            elif h2 in ("volume","vol.","vol"): idx["volume"] = i
        if "date" not in idx:
            idx["date"] = 0
        required = {"date","open","high","low","close","volume"}
        if not required.issubset(idx):
            idx = {"date":0,"open":1,"high":2,"low":3,"close":4,"volume":5}
    else:
        idx = {"date":0,"open":1,"high":2,"low":3,"close":4,"volume":5}

    for r in data:
        try:
            d = parse_date(r[idx["date"]])
            o = fnum(r[idx["open"]]); h = fnum(r[idx["high"]]); l = fnum(r[idx["low"]])
            c = fnum(r[idx["close"]]); v = fnum(r[idx["volume"]])
        except:
            continue
        if not d or None in (o,h,l,c,v) or c <= 0 or h <= 0 or l <= 0 or v < 0:
            continue
        if d < START or d > END:
            continue
        rows.append({"date":d,"open":o,"high":h,"low":l,"close":c,"volume":v})
    rows.sort(key=lambda x:x["date"])
    ded = {}
    for r in rows: ded[r["date"]] = r
    return [ded[d] for d in sorted(ded)]

def median(vals):
    vals = sorted(vals)
    n = len(vals)
    if n == 0: return 0.0
    m = n//2
    return vals[m] if n%2 else (vals[m-1]+vals[m])/2

def evaluate_target(future, entry, target):
    tgt = entry*(1+target)
    stp = entry*(1+STOP)
    for day in future:
        hit_stop = day["low"] <= stp
        hit_tgt = day["high"] >= tgt
        if hit_stop:
            return False
        if hit_tgt:
            return True
    return False

def candidate_for_window(rows, t, n):
    if t-n < 0: return None
    base = rows[t-n:t]
    b_low = min(x["low"] for x in base)
    b_high = max(x["high"] for x in base)
    if b_low <= 0: return None
    range_pct = (b_high-b_low)/b_low
    if range_pct > MAX_BASE_RANGE:
        return None
    closes = [x["close"] for x in base]
    min_close_i = min(range(len(closes)), key=lambda i: closes[i])
    if min_close_i >= len(base)-3:
        return None
    pre_close = base[-1]["close"]
    lift = pre_close/b_low - 1
    if lift < LIFT_MIN or lift > LIFT_MAX:
        return None
    if len(base) < 5:
        return None
    early_low = min(x["low"] for x in base[:-3])
    late_low = min(x["low"] for x in base[-3:])
    if not (late_low > early_low):
        return None
    med_vol = median([x["volume"] for x in base])
    avg3 = sum(x["volume"] for x in base[-3:])/3
    if med_vol <= 0 or avg3 < VOL_MULT*med_vol:
        return None
    br = rows[t]
    if br["close"] <= b_high:
        return None
    if br["close"]/base[-1]["close"] - 1 > 0.25:
        return None
    med_value = median([x["close"]*x["volume"] for x in base])
    return {
        "base_n":n, "base_low":b_low, "base_high":b_high,
        "range_pct":range_pct, "lift_pct":lift, "avg3_vol":avg3,
        "median_base_vol":med_vol, "median_base_value":med_value
    }

def test_symbol(symbol, rows):
    signals=[]
    next_allowed = MAX_BASE
    t = MAX_BASE
    while t < len(rows)-HORIZON:
        if t < next_allowed:
            t += 1; continue
        matches=[]
        for n in range(MIN_BASE, MAX_BASE+1):
            c = candidate_for_window(rows, t, n)
            if c: matches.append(c)
        if matches:
            c = max(matches, key=lambda x:x["base_n"])
            entry = rows[t]["close"]
            future = rows[t+1:t+1+HORIZON]
            out = {f"success_{int(target*100)}": evaluate_target(future, entry, target) for target in TARGETS}
            max_high = max(x["high"] for x in future)
            min_low = min(x["low"] for x in future)
            signal = {
                "symbol":symbol, "date":rows[t]["date"], "entry":entry,
                **c, **out,
                "max_return_10d": max_high/entry-1,
                "min_return_10d": min_low/entry-1,
                "liquid_1m": c["median_base_value"] >= LIQUIDITY_DAILY_VALUE,
            }
            signals.append(signal)
            next_allowed = t + COOLDOWN + 1
        t += 1
    return signals

def main():
    root = os.environ.get("EGX_DATA_ROOT","egxdata/Dataset/raw")
    files = sorted(glob.glob(os.path.join(root, "*", "*.csv")))
    all_signals=[]
    symbol_stats=[]
    tested=0
    skipped=[]
    for path in files:
        symbol = os.path.basename(path).split(".")[0].upper()
        rows = load_csv(path)
        if len(rows) < MAX_BASE + HORIZON + 5:
            skipped.append({"symbol":symbol,"rows":len(rows)})
            continue
        tested += 1
        sigs = test_symbol(symbol, rows)
        all_signals.extend(sigs)
        symbol_stats.append({
            "symbol":symbol, "rows":len(rows), "signals":len(sigs),
            "wins_8":sum(1 for s in sigs if s["success_8"])
        })

    def summarize(sigs):
        n=len(sigs)
        uniq=len(set(s["symbol"] for s in sigs))
        def cnt(k): return sum(1 for s in sigs if s[k])
        ret=sorted(s["max_return_10d"] for s in sigs)
        med=median(ret) if ret else None
        avg=(sum(ret)/len(ret)) if ret else None
        return {
            "signals":n,
            "unique_symbols_with_signal":uniq,
            "wins_5":cnt("success_5"),
            "wins_8":cnt("success_8"),
            "wins_10":cnt("success_10"),
            "win_rate_5":cnt("success_5")/n if n else None,
            "win_rate_8":cnt("success_8")/n if n else None,
            "win_rate_10":cnt("success_10")/n if n else None,
            "avg_max_return_10d":avg,
            "median_max_return_10d":med,
        }

    liquid=[s for s in all_signals if s["liquid_1m"]]
    winning_symbols=sorted(set(s["symbol"] for s in all_signals if s["success_8"]))
    liquid_winning_symbols=sorted(set(s["symbol"] for s in liquid if s["success_8"]))

    result = {
        "pattern":"Defensive Lift v1",
        "data_window":{"start":START,"end":END},
        "dataset_files_found":len(files),
        "stocks_tested":tested,
        "stocks_skipped":len(skipped),
        "rules":{
            "base_sessions":[MIN_BASE,MAX_BASE],
            "max_base_range_pct":MAX_BASE_RANGE,
            "defensive_lift_pct":[LIFT_MIN,LIFT_MAX],
            "no_new_closing_low":"minimum close not in final 3 base sessions",
            "higher_low":"min low of last 3 base sessions > min low of earlier base",
            "volume":"avg volume final 3 base sessions >= 1.5x median base volume",
            "breakout":"breakout-day close > highest high of prior base",
            "cooldown_sessions":COOLDOWN,
            "outcome":"target before -4% stop within next 10 sessions; same-bar target+stop counted as stop first",
            "liquidity_filter":"median base daily value >= 1,000,000 EGP"
        },
        "all":summarize(all_signals),
        "liquid_1m":summarize(liquid),
        "winning_symbols_8":winning_symbols,
        "liquid_winning_symbols_8":liquid_winning_symbols,
        "top_symbols_by_signal_count":sorted(symbol_stats,key=lambda x:(x["signals"],x["wins_8"]),reverse=True)[:50],
        "skipped":skipped,
        "signals":all_signals
    }
    os.makedirs("tmp/egx_backtest", exist_ok=True)
    with open("tmp/egx_backtest/results.json","w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ("pattern","data_window","dataset_files_found","stocks_tested","stocks_skipped","all","liquid_1m")}, indent=2))
    print("Winning symbols @8%:", ",".join(winning_symbols))

if __name__ == "__main__":
    main()
