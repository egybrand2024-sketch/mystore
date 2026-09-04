# Defensive Lift v5.17 — Frozen OOS Test 1

## Freeze

v5.17 is frozen at commit `236519236da35fa19dfd4dc02b1cd332f8c4b0c9` and mirrored to branch `frozen-egx-defensive-lift-v517-20260904`.

No model rule, threshold, atom, target, stop, horizon, slot count, sizing rule, same-bar policy, or friction assumption was changed for this OOS test.

Frozen reject ensemble (ANY atom rejects an otherwise accepted v3.2 trade):

1. `rs20 >= 0.07340059829329726` AND `market5_ret >= 0.008543451793102896`
2. `lift >= 0.05965902346208485` AND `gap <= -3.413044438183023e-08`
3. `lift <= 0.04764147846387261` AND `compression_ratio >= 1.139118181416062`

## Fresh OOS protocol

- Previous research dataset maximum: 2026-02-04.
- Fresh OOS starts: 2026-02-05.
- Fresh source: Yahoo Finance through yfinance, `.CA` tickers, `auto_adjust=True`.
- Fresh history downloaded from 2025-09-01 for indicator warm-up and internally consistent adjusted prices; only trades entered from 2026-02-05 onward are scored.
- Latest usable fresh date returned: 2026-09-02.
- Reference universe: 198 historical dataset symbols.
- Usable fresh Yahoo symbols: 181 (91.41% coverage); 180 had data within the latest 7 calendar days.
- Same-bar ambiguity remains stop-first.
- Round-trip friction sensitivity remains 0.5%.
- No OOS tuning or selection is allowed.

## First frozen OOS result

Closed accepted trades: 19 (7 targets, 8 stops, 4 timeouts).

| Metric | v3.2 baseline | frozen v5.17 |
|---|---:|---:|
| Return | +19.7541% | **+23.1498%** |
| Max DD | -14.0722% | **-8.2426%** |
| Final equity from 100k | 119,754.07 | **123,149.85** |

Frozen v5.17 therefore improved return by **+3.3958 percentage points** and improved max drawdown by **+5.8296 percentage points** versus v3.2 on the exact same fresh accepted-trade set.

Strict comparison result: **PASS_STRICT_VS_V32** (higher return and lower absolute max drawdown).

## Gate behavior on genuinely new trades

The frozen gate triggered on 7 of the 19 accepted trades:

- AMOC 2026-02-17: stop, Atom 3
- MENA 2026-04-14: timeout +2.65%, Atom 1
- ALUM 2026-05-03: target +12%, Atom 3
- ZMID 2026-05-13: stop, Atom 1
- ELKA 2026-06-02: timeout -1.61%, Atom 1
- UEFM 2026-06-24: stop, Atom 3
- MIPH 2026-07-15: timeout +0.16%, Atom 1

So the gate avoided three full stops and one losing timeout, but also rejected one +12% winner and two positive timeouts. Net portfolio effect was still positive in both return and drawdown.

## Interpretation

This is the first genuinely post-design OOS window for frozen v5.17 and is materially stronger evidence than the historical champion search. It is still only one OOS window with 19 closed accepted trades and seven gate triggers, so it is preliminary rather than conclusive evidence of a durable edge.

The model remains frozen after this result. Future tests must append new unseen data without modifying the frozen rules.
