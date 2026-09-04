import csv, glob, json, math, os, sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, "tmp/egx_backtest")
import backtest_v3_ml as v3

FINAL = ("2025-01-01", "2026-02-28")
TARGET = 0.12
STOP = 0.045
HORIZON = 15
INITIAL_CAPITAL = 100_000.0
FRICTIONS = [0.0, 0.0025, 0.0050, 0.0100]  # total round-trip friction sensitivity
SLOT_COUNTS = [1, 2, 3, 5, 10]


def in_period(d, p=FINAL):
    return p[0] <= d <= p[1]


def collect_v2_trades(sym, rows, market, max_h=HORIZON):
    out = []
    next_allowed = v3.MAX_BASE
    t = max(v3.MAX_BASE, 60)
    while t < len(rows) - max_h:
        if t < next_allowed:
            t += 1
            continue
        matches = []
        for n in range(v3.MIN_BASE, v3.MAX_BASE + 1):
            c = v3.v1_candidate(rows, t, n)
            if c:
                matches.append(c)
        if matches:
            c = max(matches, key=lambda x: x["base_n"])
            s = v3.make_signal(sym, rows, t, c, market)
            if s and s["v2_flag"] > 0:
                out.append({
                    "symbol": sym,
                    "entry_date": rows[t]["date"],
                    "entry": rows[t]["close"],
                    "median_base_value": c["median_base_value"],
                    "future": rows[t + 1:t + 1 + max_h],
                })
            next_allowed = t + v3.COOLDOWN + 1
        t += 1
    return out


def finalize_trade(tr):
    entry = tr["entry"]
    tgt = entry * (1 + TARGET)
    stp = entry * (1 - STOP)
    future = tr["future"][:HORIZON]
    for d in future:
        # Conservative daily-bar ambiguity: stop first if both touched.
        if d["low"] <= stp:
            return {
                **{k: tr[k] for k in ["symbol", "entry_date", "entry", "median_base_value"]},
                "exit_date": d["date"], "exit_price": stp, "gross_return": -STOP,
                "exit_type": "stop", "holding_sessions": future.index(d) + 1,
            }
        if d["high"] >= tgt:
            return {
                **{k: tr[k] for k in ["symbol", "entry_date", "entry", "median_base_value"]},
                "exit_date": d["date"], "exit_price": tgt, "gross_return": TARGET,
                "exit_type": "target", "holding_sessions": future.index(d) + 1,
            }
    d = future[-1]
    return {
        **{k: tr[k] for k in ["symbol", "entry_date", "entry", "median_base_value"]},
        "exit_date": d["date"], "exit_price": d["close"], "gross_return": d["close"] / entry - 1,
        "exit_type": "timeout", "holding_sessions": HORIZON,
    }


def longest_losing_streak(returns):
    best = cur = 0
    for r in returns:
        if r < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def max_drawdown(curve):
    peak = -1.0
    max_dd = 0.0
    peak_date = trough_date = None
    running_peak_date = None
    for row in curve:
        eq = row["equity"]
        if eq > peak:
            peak = eq
            running_peak_date = row["date"]
        dd = eq / peak - 1 if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
            peak_date = running_peak_date
            trough_date = row["date"]
    return max_dd, peak_date, trough_date


def overlap_stats(trades):
    events = defaultdict(lambda: {"entries": 0, "exits": 0})
    for tr in trades:
        events[tr["entry_date"]]["entries"] += 1
        events[tr["exit_date"]]["exits"] += 1
    active = 0
    max_active = 0
    daily = []
    for d in sorted(events):
        # Exits are intraday; new signals enter at close, so exits free capacity first.
        active -= events[d]["exits"]
        active = max(active, 0)
        active += events[d]["entries"]
        max_active = max(max_active, active)
        daily.append((d, active))
    counts = [x[1] for x in daily]
    return {
        "max_concurrent": max_active,
        "event_days": len(daily),
        "avg_concurrent_on_event_days": sum(counts) / len(counts) if counts else 0.0,
        "days_ge_2": sum(1 for x in counts if x >= 2),
        "days_ge_3": sum(1 for x in counts if x >= 3),
        "days_ge_5": sum(1 for x in counts if x >= 5),
    }


def build_close_maps(data):
    close_by_symbol = {}
    global_dates = set()
    for sym, rows in data.items():
        m = {r["date"]: r["close"] for r in rows}
        close_by_symbol[sym] = m
        global_dates.update(m)
    return close_by_symbol, sorted(global_dates)


def simulate_portfolio(trades, data, slots, friction):
    # Same-day tie-break is median base traded value descending. This is deterministic and
    # uses only information available before/at entry; it is not optimized on outcomes.
    entries_by_date = defaultdict(list)
    exits_by_date = defaultdict(list)
    for tr in trades:
        entries_by_date[tr["entry_date"]].append(tr)
        exits_by_date[tr["exit_date"]].append(tr)
    for d in entries_by_date:
        entries_by_date[d].sort(key=lambda x: (-x["median_base_value"], x["symbol"]))

    close_maps, all_dates = build_close_maps(data)
    if not trades:
        return None
    start = min(t["entry_date"] for t in trades)
    end = max(t["exit_date"] for t in trades)
    dates = [d for d in all_dates if start <= d <= end]

    half = friction / 2.0
    cash = INITIAL_CAPITAL
    open_pos = {}  # symbol -> position; v2 cooldown prevents same-symbol overlap in practice
    last_close = {}
    curve = []
    realized = []
    entered = []
    skipped = []
    max_open = 0
    exposure_samples = []

    def mark_equity(date):
        nonlocal cash
        pos_value = 0.0
        for sym, p in open_pos.items():
            px = close_maps.get(sym, {}).get(date)
            if px is not None:
                last_close[sym] = px
            px = last_close.get(sym, p["entry"])
            pos_value += p["shares"] * px
        eq = cash + pos_value
        exposure = pos_value / eq if eq > 0 else 0.0
        return eq, pos_value, exposure

    for d in dates:
        # Refresh closes before exits/entries where available.
        for sym in list(open_pos):
            px = close_maps.get(sym, {}).get(d)
            if px is not None:
                last_close[sym] = px

        # Exit before close entries on the same day.
        if d in exits_by_date:
            for tr in sorted(exits_by_date[d], key=lambda x: x["symbol"]):
                sym = tr["symbol"]
                if sym not in open_pos:
                    continue
                p = open_pos.pop(sym)
                proceeds = p["shares"] * tr["exit_price"] * (1 - half)
                cash += proceeds
                net_ret = proceeds / p["slot_budget"] - 1
                realized.append({
                    "symbol": sym, "entry_date": p["entry_date"], "exit_date": d,
                    "gross_return": tr["gross_return"], "net_return": net_ret,
                    "exit_type": tr["exit_type"], "holding_sessions": tr["holding_sessions"],
                    "slot_budget": p["slot_budget"],
                })

        if d in entries_by_date:
            for tr in entries_by_date[d]:
                if len(open_pos) >= slots:
                    skipped.append({"symbol": tr["symbol"], "date": d, "reason": "no_free_slot"})
                    continue
                eq, _, _ = mark_equity(d)
                desired_budget = eq / slots
                slot_budget = min(desired_budget, cash)
                if slot_budget <= max(1.0, eq * 0.001):
                    skipped.append({"symbol": tr["symbol"], "date": d, "reason": "insufficient_cash"})
                    continue
                # Entry half-friction consumes part of the allocated slot budget.
                invested = slot_budget * (1 - half)
                shares = invested / tr["entry"]
                cash -= slot_budget
                open_pos[tr["symbol"]] = {
                    "symbol": tr["symbol"], "entry": tr["entry"], "entry_date": d,
                    "shares": shares, "slot_budget": slot_budget,
                }
                last_close[tr["symbol"]] = tr["entry"]
                entered.append({"symbol": tr["symbol"], "date": d, "slot_budget": slot_budget})

        eq, pos_val, exposure = mark_equity(d)
        max_open = max(max_open, len(open_pos))
        exposure_samples.append(exposure)
        curve.append({
            "date": d, "equity": eq, "cash": cash, "position_value": pos_val,
            "open_positions": len(open_pos), "gross_exposure": exposure,
        })

    # Sanity: all selected positions should be closed by the final exit date.
    if open_pos:
        raise RuntimeError(f"Open positions remain after simulation: {list(open_pos)}")

    dd, dd_peak_date, dd_trough_date = max_drawdown(curve)
    final_eq = curve[-1]["equity"] if curve else INITIAL_CAPITAL
    total_ret = final_eq / INITIAL_CAPITAL - 1
    d0 = datetime.fromisoformat(curve[0]["date"]).date()
    d1 = datetime.fromisoformat(curve[-1]["date"]).date()
    years = max((d1 - d0).days / 365.25, 1 / 365.25)
    cagr = (final_eq / INITIAL_CAPITAL) ** (1 / years) - 1 if final_eq > 0 else -1.0
    net_returns = [x["net_return"] for x in realized]
    return {
        "slots": slots,
        "round_trip_friction": friction,
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": final_eq,
        "total_return": total_ret,
        "cagr_from_first_entry_to_last_exit": cagr,
        "max_drawdown": dd,
        "drawdown_peak_date": dd_peak_date,
        "drawdown_trough_date": dd_trough_date,
        "signals_available": len(trades),
        "trades_entered": len(realized),
        "trades_skipped": len(skipped),
        "max_open_positions": max_open,
        "avg_gross_exposure": sum(exposure_samples) / len(exposure_samples) if exposure_samples else 0.0,
        "avg_net_return_per_entered_trade": sum(net_returns) / len(net_returns) if net_returns else None,
        "median_net_return_per_entered_trade": v3.median(net_returns) if net_returns else None,
        "positive_trade_rate_net": sum(1 for x in net_returns if x > 0) / len(net_returns) if net_returns else None,
        "longest_losing_streak_net": longest_losing_streak(net_returns),
        "targets": sum(1 for x in realized if x["exit_type"] == "target"),
        "stops": sum(1 for x in realized if x["exit_type"] == "stop"),
        "timeouts": sum(1 for x in realized if x["exit_type"] == "timeout"),
        "curve": curve,
        "realized_trades": realized,
        "skipped": skipped,
    }


def sequence_stats(trades, friction):
    half = friction / 2
    ordered = sorted(trades, key=lambda x: (x["entry_date"], x["symbol"]))
    # Approximate standalone net trade return using symmetric half-friction on entry/exit.
    net = [((1 - half) * (1 + t["gross_return"]) * (1 - half) - 1) for t in ordered]
    return {
        "round_trip_friction": friction,
        "trades": len(ordered),
        "avg_net_trade_return": sum(net) / len(net) if net else None,
        "median_net_trade_return": v3.median(net) if net else None,
        "positive_rate_net": sum(1 for x in net if x > 0) / len(net) if net else None,
        "longest_losing_streak": longest_losing_streak(net),
    }


def main():
    root = os.environ.get("EGX_DATA_ROOT", "egxdata/Dataset/raw")
    files = sorted(glob.glob(os.path.join(root, "*", "*.csv")))
    data = {}
    for p in files:
        sym = os.path.basename(p).split(".")[0].upper()
        rows = v3.load_csv_all(p)
        if len(rows) >= 100:
            data[sym] = rows
    market = v3.build_market_maps(data)

    raw = []
    for sym, rows in data.items():
        raw.extend(collect_v2_trades(sym, rows, market, HORIZON))
    final_raw = [x for x in raw if in_period(x["entry_date"])]
    final_trades = [finalize_trade(x) for x in final_raw]
    final_trades.sort(key=lambda x: (x["entry_date"], x["symbol"]))

    overlap = overlap_stats(final_trades)
    all_capacity_slots = max(overlap["max_concurrent"], 1)
    slots_to_test = SLOT_COUNTS + ([all_capacity_slots] if all_capacity_slots not in SLOT_COUNTS else [])

    scenarios = []
    reference_curve = None
    reference_realized = None
    for friction in FRICTIONS:
        for slots in slots_to_test:
            sim = simulate_portfolio(final_trades, data, slots, friction)
            # Keep full curve only for the reference scenario to keep JSON compact.
            is_reference = (slots == 5 and abs(friction - 0.005) < 1e-12)
            if is_reference:
                reference_curve = sim["curve"]
                reference_realized = sim["realized_trades"]
            slim = {k: v for k, v in sim.items() if k not in {"curve", "realized_trades", "skipped"}}
            scenarios.append(slim)

    seq = [sequence_stats(final_trades, f) for f in FRICTIONS]
    result = {
        "pattern": "Defensive Lift v3.1 portfolio research",
        "strategy": {
            "entry": "frozen Defensive Lift v2 signal at breakout close",
            "target": TARGET, "stop": STOP, "max_holding_sessions": HORIZON,
            "same_bar_target_stop": "stop first",
        },
        "period": FINAL,
        "dataset": {"files_found": len(files), "stocks_loaded": len(data), "available_v3_trades": len(final_trades)},
        "portfolio_method": {
            "initial_capital_egp": INITIAL_CAPITAL,
            "position_sizing": "each new position receives approximately current equity / max_positions, limited by cash",
            "same_day_capacity_tie_break": "higher historical median base traded value first; then symbol alphabetically",
            "exit_before_new_close_entries_same_day": True,
            "friction_sensitivity_total_round_trip": FRICTIONS,
            "max_position_scenarios": slots_to_test,
            "note": "friction levels are sensitivity assumptions, not claimed broker/exchange fee schedules",
        },
        "overlap": overlap,
        "sequence_stats_all_signals": seq,
        "scenarios": scenarios,
        "reference_scenario": {
            "slots": 5, "round_trip_friction": 0.005,
            "interpretation": "20% capital slot; full -4.5% stop corresponds to about 0.9% portfolio risk before friction when fully sized",
        },
    }
    with open("tmp/egx_backtest/results_v31_portfolio.json", "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    if reference_curve:
        with open("tmp/egx_backtest/equity_curve_v31_reference.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(reference_curve[0].keys()))
            w.writeheader(); w.writerows(reference_curve)
    if reference_realized:
        with open("tmp/egx_backtest/trades_v31_reference.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(reference_realized[0].keys()))
            w.writeheader(); w.writerows(reference_realized)

    # Print compact summary only.
    ref = next((x for x in scenarios if x["slots"] == 5 and abs(x["round_trip_friction"] - 0.005) < 1e-12), None)
    no_cost = next((x for x in scenarios if x["slots"] == 5 and x["round_trip_friction"] == 0.0), None)
    allcap = next((x for x in scenarios if x["slots"] == all_capacity_slots and abs(x["round_trip_friction"] - 0.005) < 1e-12), None)
    compact = {
        "pattern": result["pattern"], "period": FINAL, "trades": len(final_trades),
        "overlap": overlap, "reference_5_slots_0_5pct_friction": ref,
        "same_5_slots_zero_friction": no_cost,
        "all_capacity_0_5pct_friction": allcap,
        "sequence_stats": seq,
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
