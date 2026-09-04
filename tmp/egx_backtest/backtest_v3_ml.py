import csv, glob, json, math, os, statistics, warnings
from collections import defaultdict
from datetime import datetime

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, HistGradientBoostingClassifier, GradientBoostingClassifier

warnings.filterwarnings("ignore")

START = "2021-01-01"
V1_MAX_BASE_RANGE = 0.10
LIFT_MIN = 0.03
LIFT_MAX = 0.08
PREBREAK_VOL_MULT = 1.50
MIN_BASE = 5
MAX_BASE = 15
COOLDOWN = 10
HORIZON = 10
TARGET = 0.08
STOP = -0.04

# v2 frozen robust candidate, used only as a benchmark.
V2_CFG = {
    "min_body": 0.02,
    "min_clv": 0.55,
    "max_breakout_ret": 0.06,
    "min_breakout_ret": 0.0,
    "min_vol_ratio": 2.0,
    "max_base_range": 0.08,
    "min_clearance": 0.0,
    "min_pre20_ret": -0.03,
    "max_compression_ratio": 1.25,
    "min_liquidity": 0,
}

# Model/threshold selection is restricted to 2023 and 2024 walk-forward validation.
FOLD_A_TRAIN = ("2021-01-01", "2022-12-31")
FOLD_A_VALID = ("2023-01-01", "2023-12-31")
FOLD_B_TRAIN = ("2021-01-01", "2023-12-31")
FOLD_B_VALID = ("2024-01-01", "2024-12-31")
LOCK_TRAIN = ("2021-01-01", "2024-12-31")
KNOWN_OOS = ("2025-01-01", "2026-02-28")
PRISTINE_START = "2026-03-01"

FEATURES = [
    "base_n", "base_range", "lift", "prebreak_vol_ratio", "log_liquidity",
    "body", "clv", "body_to_range", "upper_wick", "lower_wick",
    "breakout_ret", "gap", "clearance", "breakout_vol_ratio", "breakout_range_pct",
    "breakout_range_atr20", "compression_ratio", "base_vs_prior_atr",
    "pre5_ret", "pre10_ret", "pre20_ret", "pre60_ret",
    "rs5", "rs20", "market5_ret", "market20_ret", "market_breadth20",
    "dist_20_high", "dist_60_high", "breakout_vs_60_high", "nearest_overhead_pct",
    "close_vs_sma20", "close_vs_sma50", "slope10", "base_close_slope", "base_low_slope",
    "up_volume_share", "resistance_touches", "max_abs_ret60", "v2_flag"
]


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
    except Exception:
        return None


def parse_date(v):
    s = str(v).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except Exception:
            pass
    return None


def load_csv_all(path):
    rows = []
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except Exception:
            dialect = csv.excel
        raw = list(csv.reader(fh, dialect))
    if not raw:
        return rows
    header = [str(x).strip().lower() for x in raw[0]]
    has_header = any(x in header for x in ("date", "open", "high", "low", "close", "volume"))
    data = raw[1:] if has_header else raw
    if has_header:
        idx = {}
        for i, h in enumerate(header):
            if h in ("date", "datetime", "timestamp"):
                idx["date"] = i
            elif h == "open":
                idx["open"] = i
            elif h == "high":
                idx["high"] = i
            elif h == "low":
                idx["low"] = i
            elif h in ("close", "price", "adj close", "adj_close"):
                idx["close"] = i
            elif h in ("volume", "vol.", "vol"):
                idx["volume"] = i
        if "date" not in idx:
            idx["date"] = 0
        if not {"date", "open", "high", "low", "close", "volume"}.issubset(idx):
            idx = {"date": 0, "open": 1, "high": 2, "low": 3, "close": 4, "volume": 5}
    else:
        idx = {"date": 0, "open": 1, "high": 2, "low": 3, "close": 4, "volume": 5}

    for r in data:
        try:
            d = parse_date(r[idx["date"]])
            o = fnum(r[idx["open"]]); h = fnum(r[idx["high"]]); l = fnum(r[idx["low"]])
            c = fnum(r[idx["close"]]); v = fnum(r[idx["volume"]])
        except Exception:
            continue
        if not d or None in (o, h, l, c, v) or min(o, h, l, c) <= 0 or v < 0:
            continue
        if d < START:
            continue
        rows.append({"date": d, "open": o, "high": h, "low": l, "close": c, "volume": v})
    rows.sort(key=lambda x: x["date"])
    ded = {r["date"]: r for r in rows}
    return [ded[d] for d in sorted(ded)]


def median(vals):
    vals = [x for x in vals if x is not None and math.isfinite(x)]
    return statistics.median(vals) if vals else 0.0


def mean(vals):
    vals = [x for x in vals if x is not None and math.isfinite(x)]
    return sum(vals) / len(vals) if vals else 0.0


def lin_slope(values):
    vals = [float(v) for v in values]
    n = len(vals)
    if n < 2:
        return 0.0
    xm = (n - 1) / 2
    ym = sum(vals) / n
    den = sum((i - xm) ** 2 for i in range(n))
    if den <= 0 or abs(ym) < 1e-12:
        return 0.0
    num = sum((i - xm) * (vals[i] - ym) for i in range(n))
    return (num / den) / abs(ym)


def returns(rows):
    out = []
    for i in range(1, len(rows)):
        p = rows[i - 1]["close"]
        out.append(rows[i]["close"] / p - 1 if p > 0 else 0.0)
    return out


def true_range_pct(rows, i):
    if i <= 0:
        return (rows[i]["high"] - rows[i]["low"]) / rows[i]["close"]
    prev = rows[i - 1]["close"]
    tr = max(rows[i]["high"] - rows[i]["low"], abs(rows[i]["high"] - prev), abs(rows[i]["low"] - prev))
    return tr / prev if prev > 0 else 0.0


def build_market_maps(data):
    daily = defaultdict(list)
    for symbol, rows in data.items():
        for i in range(1, len(rows)):
            prev = rows[i - 1]["close"]
            if prev > 0:
                r = rows[i]["close"] / prev - 1
                # Ignore obviously broken corporate-action artifacts in the market aggregate.
                if -0.35 <= r <= 0.35:
                    daily[rows[i]["date"]].append(r)
    dates = sorted(daily)
    market_ret = {}
    breadth = {}
    for d in dates:
        vals = daily[d]
        market_ret[d] = median(vals)
        breadth[d] = sum(1 for x in vals if x > 0) / len(vals) if vals else 0.5
    idx = 1.0
    idx_map = {}
    for d in dates:
        idx *= max(0.01, 1 + market_ret[d])
        idx_map[d] = idx
    pos = {d: i for i, d in enumerate(dates)}
    def period_ret(d, n):
        i = pos.get(d)
        if i is None or i < n:
            return 0.0
        a = idx_map[dates[i - n]]
        b = idx_map[d]
        return b / a - 1 if a > 0 else 0.0
    market5 = {d: period_ret(d, 5) for d in dates}
    market20 = {d: period_ret(d, 20) for d in dates}
    breadth20 = {}
    for i, d in enumerate(dates):
        lo = max(0, i - 19)
        breadth20[d] = mean([breadth[dates[j]] for j in range(lo, i + 1)])
    return {"dates": dates, "ret": market_ret, "m5": market5, "m20": market20, "breadth20": breadth20}


def v1_candidate(rows, t, n):
    if t - n < 0:
        return None
    base = rows[t - n:t]
    b_low = min(x["low"] for x in base)
    b_high = max(x["high"] for x in base)
    if b_low <= 0:
        return None
    range_pct = (b_high - b_low) / b_low
    if range_pct > V1_MAX_BASE_RANGE:
        return None
    closes = [x["close"] for x in base]
    min_close_i = min(range(len(closes)), key=lambda i: closes[i])
    if min_close_i >= len(base) - 3:
        return None
    lift = base[-1]["close"] / b_low - 1
    if not (LIFT_MIN <= lift <= LIFT_MAX):
        return None
    early_low = min(x["low"] for x in base[:-3])
    late_low = min(x["low"] for x in base[-3:])
    if not late_low > early_low:
        return None
    med_vol = median([x["volume"] for x in base])
    avg3 = mean([x["volume"] for x in base[-3:]])
    if med_vol <= 0 or avg3 < PREBREAK_VOL_MULT * med_vol:
        return None
    br = rows[t]
    if br["close"] <= b_high:
        return None
    if br["close"] / base[-1]["close"] - 1 > 0.25:
        return None
    med_value = median([x["close"] * x["volume"] for x in base])
    return {
        "base": base, "base_n": n, "base_low": b_low, "base_high": b_high,
        "range_pct": range_pct, "lift": lift, "med_vol": med_vol,
        "avg3": avg3, "median_base_value": med_value,
    }


def outcome(future, entry):
    tgt = entry * (1 + TARGET)
    stp = entry * (1 + STOP)
    for d in future:
        if d["low"] <= stp:
            return False, STOP, "stop"
        if d["high"] >= tgt:
            return True, TARGET, "target"
    last_ret = future[-1]["close"] / entry - 1 if future else 0.0
    return False, last_ret, "timeout"


def v2_pass(s):
    if s["body"] < V2_CFG["min_body"]: return False
    if s["clv"] < V2_CFG["min_clv"]: return False
    if s["breakout_ret"] > V2_CFG["max_breakout_ret"]: return False
    if s["breakout_ret"] < V2_CFG["min_breakout_ret"]: return False
    if s["breakout_vol_ratio"] < V2_CFG["min_vol_ratio"]: return False
    if s["base_range"] > V2_CFG["max_base_range"]: return False
    if s["clearance"] < V2_CFG["min_clearance"]: return False
    if s["pre20_ret"] is not None and s["pre20_ret"] < V2_CFG["min_pre20_ret"]: return False
    if s["compression_ratio"] > V2_CFG["max_compression_ratio"]: return False
    if s["median_base_value"] < V2_CFG["min_liquidity"]: return False
    return True


def make_signal(symbol, rows, t, c, market):
    br = rows[t]; prev = rows[t - 1]
    entry = br["close"]
    future = rows[t + 1:t + 1 + HORIZON]
    if len(future) < HORIZON:
        return None
    success, realized, exit_type = outcome(future, entry)
    candle_range = max(br["high"] - br["low"], 1e-12)
    body = (br["close"] - br["open"]) / br["open"]
    clv = (br["close"] - br["low"]) / candle_range
    body_to_range = (br["close"] - br["open"]) / candle_range
    upper_wick = (br["high"] - max(br["open"], br["close"])) / candle_range
    lower_wick = (min(br["open"], br["close"]) - br["low"]) / candle_range
    breakout_ret = br["close"] / prev["close"] - 1
    gap = br["open"] / prev["close"] - 1
    clearance = br["close"] / c["base_high"] - 1
    breakout_vol_ratio = br["volume"] / c["med_vol"] if c["med_vol"] > 0 else 0.0
    prebreak_vol_ratio = c["avg3"] / c["med_vol"] if c["med_vol"] > 0 else 0.0
    breakout_range_pct = candle_range / prev["close"]

    def ret_n(n):
        if t - n < 0 or rows[t - n]["close"] <= 0:
            return 0.0
        return prev["close"] / rows[t - n]["close"] - 1

    pre5 = ret_n(5); pre10 = ret_n(10); pre20 = ret_n(20); pre60 = ret_n(60)
    market5 = market["m5"].get(br["date"], 0.0)
    market20 = market["m20"].get(br["date"], 0.0)
    rs5 = pre5 - market5
    rs20 = pre20 - market20
    breadth20 = market["breadth20"].get(br["date"], 0.5)

    prior20 = rows[max(0, t - 20):t]
    prior50 = rows[max(0, t - 50):t]
    prior60 = rows[max(0, t - 60):t]
    prior120 = rows[max(0, t - 120):t]
    h20 = max(x["high"] for x in prior20) if prior20 else prev["high"]
    h60 = max(x["high"] for x in prior60) if prior60 else h20
    dist20 = prev["close"] / h20 - 1 if h20 > 0 else 0.0
    dist60 = prev["close"] / h60 - 1 if h60 > 0 else 0.0
    breakout_vs_60 = br["close"] / h60 - 1 if h60 > 0 else 0.0
    overhead = sorted([x["high"] / br["close"] - 1 for x in prior120 if x["high"] > br["close"] * 1.002])
    nearest_overhead = min(overhead[0], 0.30) if overhead else 0.30

    sma20 = mean([x["close"] for x in prior20]) if prior20 else prev["close"]
    sma50 = mean([x["close"] for x in prior50]) if prior50 else prev["close"]
    close_vs_sma20 = prev["close"] / sma20 - 1 if sma20 > 0 else 0.0
    close_vs_sma50 = prev["close"] / sma50 - 1 if sma50 > 0 else 0.0
    slope10 = lin_slope([x["close"] for x in rows[max(0, t - 10):t]])

    base = c["base"]
    base_close_slope = lin_slope([x["close"] for x in base])
    early3 = base[:3] if len(base) >= 6 else base[:2]
    late3 = base[-3:] if len(base) >= 3 else base
    base_low_slope = (mean([x["low"] for x in late3]) - mean([x["low"] for x in early3])) / c["base_low"] if c["base_low"] > 0 else 0.0
    total_vol = sum(x["volume"] for x in base)
    up_volume = sum(x["volume"] for x in base if x["close"] >= x["open"])
    up_volume_share = up_volume / total_vol if total_vol > 0 else 0.5
    resistance_touches = sum(1 for x in base if x["high"] >= c["base_high"] * 0.99)

    base_ranges = [(x["high"] - x["low"]) / x["close"] for x in base if x["close"] > 0]
    late_range = mean(base_ranges[-3:])
    early_range = mean(base_ranges[:-3]) if len(base_ranges) > 3 else late_range
    compression_ratio = late_range / early_range if early_range > 0 else 99.0

    atr20 = mean([true_range_pct(rows, i) for i in range(max(1, t - 20), t)])
    breakout_range_atr20 = breakout_range_pct / atr20 if atr20 > 0 else 99.0
    base_avg_range = mean(base_ranges)
    prior_start = max(1, t - c["base_n"] - 20)
    prior_end = max(prior_start + 1, t - c["base_n"])
    prior_atr = mean([true_range_pct(rows, i) for i in range(prior_start, prior_end)])
    base_vs_prior_atr = base_avg_range / prior_atr if prior_atr > 0 else 1.0

    r60 = []
    for i in range(max(1, t - 60), t):
        p = rows[i - 1]["close"]
        if p > 0:
            r60.append(abs(rows[i]["close"] / p - 1))
    max_abs_ret60 = max(r60) if r60 else 0.0

    s = {
        "symbol": symbol, "date": br["date"], "entry": entry,
        "base_n": c["base_n"], "base_range": c["range_pct"], "lift": c["lift"],
        "prebreak_vol_ratio": prebreak_vol_ratio, "median_base_value": c["median_base_value"],
        "log_liquidity": math.log10(max(c["median_base_value"], 1.0)),
        "body": body, "clv": clv, "body_to_range": body_to_range,
        "upper_wick": upper_wick, "lower_wick": lower_wick,
        "breakout_ret": breakout_ret, "gap": gap, "clearance": clearance,
        "breakout_vol_ratio": breakout_vol_ratio, "breakout_range_pct": breakout_range_pct,
        "breakout_range_atr20": breakout_range_atr20, "compression_ratio": compression_ratio,
        "base_vs_prior_atr": base_vs_prior_atr,
        "pre5_ret": pre5, "pre10_ret": pre10, "pre20_ret": pre20, "pre60_ret": pre60,
        "rs5": rs5, "rs20": rs20, "market5_ret": market5, "market20_ret": market20,
        "market_breadth20": breadth20,
        "dist_20_high": dist20, "dist_60_high": dist60, "breakout_vs_60_high": breakout_vs_60,
        "nearest_overhead_pct": nearest_overhead,
        "close_vs_sma20": close_vs_sma20, "close_vs_sma50": close_vs_sma50,
        "slope10": slope10, "base_close_slope": base_close_slope, "base_low_slope": base_low_slope,
        "up_volume_share": up_volume_share, "resistance_touches": resistance_touches,
        "max_abs_ret60": max_abs_ret60,
        "success": bool(success), "realized_return": realized, "exit_type": exit_type,
        "max_return": max(x["high"] for x in future) / entry - 1,
        "min_return": min(x["low"] for x in future) / entry - 1,
    }
    s["v2_flag"] = 1.0 if v2_pass(s) else 0.0
    return s


def collect_signals(symbol, rows, market):
    sigs = []
    next_allowed = MAX_BASE
    t = max(MAX_BASE, 60)
    while t < len(rows) - HORIZON:
        if t < next_allowed:
            t += 1
            continue
        matches = []
        for n in range(MIN_BASE, MAX_BASE + 1):
            c = v1_candidate(rows, t, n)
            if c:
                matches.append(c)
        if matches:
            c = max(matches, key=lambda x: x["base_n"])
            s = make_signal(symbol, rows, t, c, market)
            if s:
                sigs.append(s)
                next_allowed = t + COOLDOWN + 1
        t += 1
    return sigs


def in_period(s, period):
    return period[0] <= s["date"] <= period[1]


def summary(sigs):
    n = len(sigs)
    if not n:
        return {"signals": 0, "wins": 0, "win_rate": None, "unique_symbols": 0,
                "avg_realized_return": None, "median_realized_return": None,
                "avg_max_return": None, "avg_min_return": None, "targets": 0, "stops": 0, "timeouts": 0}
    wins = sum(1 for s in sigs if s["success"])
    return {
        "signals": n, "wins": wins, "win_rate": wins / n,
        "unique_symbols": len(set(s["symbol"] for s in sigs)),
        "avg_realized_return": mean([s["realized_return"] for s in sigs]),
        "median_realized_return": median([s["realized_return"] for s in sigs]),
        "avg_max_return": mean([s["max_return"] for s in sigs]),
        "avg_min_return": mean([s["min_return"] for s in sigs]),
        "targets": sum(1 for s in sigs if s["exit_type"] == "target"),
        "stops": sum(1 for s in sigs if s["exit_type"] == "stop"),
        "timeouts": sum(1 for s in sigs if s["exit_type"] == "timeout"),
    }


def wilson_lower(w, n, z=1.0):
    if n <= 0:
        return 0.0
    p = w / n
    den = 1 + z * z / n
    center = p + z * z / (2 * n)
    adj = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (center - adj) / den


def matrix(sigs):
    X = np.array([[s.get(f, np.nan) if s.get(f) is not None else np.nan for f in FEATURES] for s in sigs], dtype=float)
    y = np.array([1 if s["success"] else 0 for s in sigs], dtype=int)
    return X, y


def model_specs():
    return {
        "logistic_c0_3": lambda: Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(C=0.3, max_iter=3000, class_weight="balanced", random_state=42))
        ]),
        "logistic_c1": lambda: Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(C=1.0, max_iter=3000, class_weight="balanced", random_state=42))
        ]),
        "rf_d3_leaf12": lambda: Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("clf", RandomForestClassifier(n_estimators=500, max_depth=3, min_samples_leaf=12, max_features="sqrt", class_weight="balanced_subsample", random_state=42, n_jobs=-1))
        ]),
        "rf_d5_leaf10": lambda: Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("clf", RandomForestClassifier(n_estimators=600, max_depth=5, min_samples_leaf=10, max_features="sqrt", class_weight="balanced_subsample", random_state=42, n_jobs=-1))
        ]),
        "extra_d4_leaf12": lambda: Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("clf", ExtraTreesClassifier(n_estimators=600, max_depth=4, min_samples_leaf=12, max_features="sqrt", class_weight="balanced", random_state=42, n_jobs=-1))
        ]),
        "extra_d6_leaf10": lambda: Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("clf", ExtraTreesClassifier(n_estimators=600, max_depth=6, min_samples_leaf=10, max_features="sqrt", class_weight="balanced", random_state=42, n_jobs=-1))
        ]),
        "gb_d1": lambda: Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("clf", GradientBoostingClassifier(n_estimators=120, learning_rate=0.035, max_depth=1, min_samples_leaf=12, random_state=42))
        ]),
        "gb_d2": lambda: Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("clf", GradientBoostingClassifier(n_estimators=120, learning_rate=0.03, max_depth=2, min_samples_leaf=15, random_state=42))
        ]),
        "hist_leaf7": lambda: Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("clf", HistGradientBoostingClassifier(max_iter=180, learning_rate=0.04, max_leaf_nodes=7, min_samples_leaf=20, l2_regularization=2.0, random_state=42))
        ]),
        "hist_leaf15": lambda: Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("clf", HistGradientBoostingClassifier(max_iter=160, learning_rate=0.035, max_leaf_nodes=15, min_samples_leaf=20, l2_regularization=3.0, random_state=42))
        ]),
    }


def fit_scores(model_factory, train_sigs, eval_sigs):
    Xtr, ytr = matrix(train_sigs)
    Xev, _ = matrix(eval_sigs)
    model = model_factory()
    model.fit(Xtr, ytr)
    train_score = model.predict_proba(Xtr)[:, 1]
    eval_score = model.predict_proba(Xev)[:, 1]
    return model, train_score, eval_score


def percentile(vals, q):
    return float(np.quantile(np.asarray(vals, dtype=float), q))


def selected_by_score(sigs, scores, threshold):
    out = []
    for s, sc in zip(sigs, scores):
        if sc >= threshold:
            x = dict(s)
            x["model_score"] = float(sc)
            out.append(x)
    return out


def validate_config(model_name, factory, q, all_sigs):
    results = []
    for train_p, valid_p in [(FOLD_A_TRAIN, FOLD_A_VALID), (FOLD_B_TRAIN, FOLD_B_VALID)]:
        train = [s for s in all_sigs if in_period(s, train_p)]
        valid = [s for s in all_sigs if in_period(s, valid_p)]
        if len(train) < 100 or len(valid) < 20:
            return None
        _, train_score, valid_score = fit_scores(factory, train, valid)
        thr = percentile(train_score, q)
        sel = selected_by_score(valid, valid_score, thr)
        sm = summary(sel)
        if sm["signals"] < 15 or sm["unique_symbols"] < 10:
            return None
        sm["threshold"] = thr
        results.append(sm)
    lowers = [wilson_lower(r["wins"], r["signals"], z=1.0) for r in results]
    wrs = [r["win_rate"] for r in results]
    return {
        "model": model_name, "quantile": q,
        "fold_2023": results[0], "fold_2024": results[1],
        "min_wilson": min(lowers), "avg_wilson": mean(lowers),
        "min_win_rate": min(wrs), "avg_win_rate": mean(wrs),
        "combined_signals": results[0]["signals"] + results[1]["signals"],
    }


def extract_importance(model):
    try:
        clf = model.named_steps["clf"]
        if hasattr(clf, "feature_importances_"):
            vals = clf.feature_importances_
        elif hasattr(clf, "coef_"):
            vals = np.abs(clf.coef_[0])
        else:
            return []
        pairs = sorted(zip(FEATURES, [float(x) for x in vals]), key=lambda x: x[1], reverse=True)
        return [{"feature": a, "importance": b} for a, b in pairs[:20]]
    except Exception:
        return []


def sensitivity(selected):
    # Same selected entries, alternate target/stop/horizon outcomes cannot be reconstructed from the compact signal.
    # Keep this placeholder explicit rather than silently reusing the headline outcome.
    return {"note": "Headline v3 keeps the frozen +8%/-4%/10-session outcome for apples-to-apples comparison."}


def main():
    root = os.environ.get("EGX_DATA_ROOT", "egxdata/Dataset/raw")
    files = sorted(glob.glob(os.path.join(root, "*", "*.csv")))
    data = {}
    for path in files:
        symbol = os.path.basename(path).split(".")[0].upper()
        rows = load_csv_all(path)
        if len(rows) >= 100:
            data[symbol] = rows
    market = build_market_maps(data)
    max_date = max((rows[-1]["date"] for rows in data.values() if rows), default=None)
    min_date = min((rows[0]["date"] for rows in data.values() if rows), default=None)

    all_sigs = []
    for symbol, rows in data.items():
        all_sigs.extend(collect_signals(symbol, rows, market))
    all_sigs.sort(key=lambda s: (s["date"], s["symbol"]))

    v1_2023 = summary([s for s in all_sigs if in_period(s, FOLD_A_VALID)])
    v1_2024 = summary([s for s in all_sigs if in_period(s, FOLD_B_VALID)])
    v1_known = summary([s for s in all_sigs if in_period(s, KNOWN_OOS)])
    pristine_end = max_date if max_date and max_date >= PRISTINE_START else None
    pristine_period = (PRISTINE_START, pristine_end) if pristine_end else None
    v1_pristine = summary([s for s in all_sigs if pristine_period and in_period(s, pristine_period)])

    v2_2023 = summary([s for s in all_sigs if in_period(s, FOLD_A_VALID) and s["v2_flag"] > 0])
    v2_2024 = summary([s for s in all_sigs if in_period(s, FOLD_B_VALID) and s["v2_flag"] > 0])
    v2_known = summary([s for s in all_sigs if in_period(s, KNOWN_OOS) and s["v2_flag"] > 0])
    v2_pristine = summary([s for s in all_sigs if pristine_period and in_period(s, pristine_period) and s["v2_flag"] > 0])

    quantiles = [0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.95, 0.96]
    ranked = []
    specs = model_specs()
    for name, factory in specs.items():
        for q in quantiles:
            r = validate_config(name, factory, q, all_sigs)
            if r:
                ranked.append(r)
    ranked.sort(key=lambda r: (r["min_wilson"], r["avg_wilson"], r["min_win_rate"], r["combined_signals"]), reverse=True)
    if not ranked:
        raise RuntimeError("No eligible v3 model configuration")
    best = ranked[0]
    best_name = best["model"]
    best_q = best["quantile"]

    lock_train = [s for s in all_sigs if in_period(s, LOCK_TRAIN)]
    known = [s for s in all_sigs if in_period(s, KNOWN_OOS)]
    pristine = [s for s in all_sigs if pristine_period and in_period(s, pristine_period)]
    model, lock_scores, known_scores = fit_scores(specs[best_name], lock_train, known)
    final_threshold = percentile(lock_scores, best_q)
    v3_known_sigs = selected_by_score(known, known_scores, final_threshold)
    if pristine:
        Xp, _ = matrix(pristine)
        pristine_scores = model.predict_proba(Xp)[:, 1]
        v3_pristine_sigs = selected_by_score(pristine, pristine_scores, final_threshold)
    else:
        v3_pristine_sigs = []

    v3_known = summary(v3_known_sigs)
    v3_pristine = summary(v3_pristine_sigs)

    target_relative_to_v2 = (v2_known["win_rate"] * 1.30) if v2_known["win_rate"] is not None else None
    known_relative_improvement = (v3_known["win_rate"] / v2_known["win_rate"] - 1) if v3_known["win_rate"] is not None and v2_known["win_rate"] else None
    pristine_relative_improvement = (v3_pristine["win_rate"] / v2_pristine["win_rate"] - 1) if v3_pristine["win_rate"] is not None and v2_pristine["win_rate"] else None

    result = {
        "pattern": "Defensive Lift v3 expanded research",
        "dataset": {
            "files_found": len(files), "stocks_loaded": len(data), "data_start": min_date, "data_max_date": max_date,
            "signals_total": len(all_sigs), "pristine_period": pristine_period,
        },
        "objective": {
            "headline_metric": "+8% before -4% within 10 sessions, same-bar stop-first",
            "requested_min_relative_improvement_vs_v2": 0.30,
            "v2_known_oos_win_rate": v2_known["win_rate"],
            "target_win_rate_if_interpreted_as_30pct_relative": target_relative_to_v2,
            "anti_overfit": "model family + selection quantile chosen only from walk-forward 2023/2024; 2025+ not used in algorithmic model/quantile selection",
        },
        "features": FEATURES,
        "benchmarks": {
            "v1_2023": v1_2023, "v2_2023": v2_2023,
            "v1_2024": v1_2024, "v2_2024": v2_2024,
            "v1_known_2025_to_feb2026": v1_known, "v2_known_2025_to_feb2026": v2_known,
            "v1_pristine_post_feb2026": v1_pristine, "v2_pristine_post_feb2026": v2_pristine,
        },
        "selection": {
            "eligible_model_quantile_configs": len(ranked),
            "selected": best,
            "top20": ranked[:20],
            "locked_train_period": LOCK_TRAIN,
            "locked_threshold": final_threshold,
        },
        "v3_known_2025_to_feb2026": v3_known,
        "v3_pristine_post_feb2026": v3_pristine,
        "known_relative_improvement_vs_v2": known_relative_improvement,
        "pristine_relative_improvement_vs_v2": pristine_relative_improvement,
        "meets_30pct_relative_target_known_oos": bool(known_relative_improvement is not None and known_relative_improvement >= 0.30),
        "meets_30pct_relative_target_pristine": bool(pristine_relative_improvement is not None and pristine_relative_improvement >= 0.30),
        "feature_importance": extract_importance(model),
        "v3_known_signals": v3_known_sigs,
        "v3_pristine_signals": v3_pristine_sigs,
        "sensitivity": sensitivity(v3_known_sigs),
    }
    os.makedirs("tmp/egx_backtest", exist_ok=True)
    with open("tmp/egx_backtest/results_v3_ml.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    compact = {k: result[k] for k in ["pattern", "dataset", "objective", "benchmarks", "selection", "v3_known_2025_to_feb2026", "v3_pristine_post_feb2026", "known_relative_improvement_vs_v2", "pristine_relative_improvement_vs_v2", "meets_30pct_relative_target_known_oos", "meets_30pct_relative_target_pristine", "feature_importance"]}
    compact["selection"] = {"eligible_model_quantile_configs": len(ranked), "selected": best, "locked_threshold": final_threshold}
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
