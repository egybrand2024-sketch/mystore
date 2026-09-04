# Defensive Lift v5.8 — Selective Hazard Gate

## Status

**Rejected Research Version.**

`v3.2` remains the **High-Return Research Reference**.

This version is frozen independently. It does not modify v3.2, v5.6, or v5.7 retroactively.

## Research question

v5.7 showed that applying a probe-first structure to every DLP signal can reduce drawdown, but it cuts too much return. v5.8 therefore tests a narrower hypothesis:

> Keep normal v3.2 trades unchanged at the full 50% slot, and apply staged protection only to a small subset that looks hazardous **before entry**.

The objective is to preserve the right tail while reducing damage from early failed breakouts.

## Fixed v3.2 components

- Entry signal: frozen v2 DLP.
- Target: +12%.
- Stop: -4.5%.
- Holding horizon: 7 sessions.
- Maximum positions: 2.
- Normal slot size: 50% of equity.
- Ranking: v3.2 liquidity ranking.
- Round-trip friction sensitivity: 0.5%.
- Same-bar target/stop ambiguity: stop-first.

## Selective protection design

Normal signals keep the full 50% entry immediately.

Only signals classified as `hazard` start with a smaller probe. On the first session after entry, the probe may be restored toward the full 50% size if continuation is confirmed.

### Fixed pre-entry hazard flags

All are known at or before entry:

- Weak breadth: `breadth20 <= 40%`.
- Weak 20-session market context: `market20 <= -2%`.
- Weak relative strength: `rs20 <= 0`.
- Extended breakout: `breakout_ret >= 4%`.
- Tight overhead room: `nearest_overhead <= 3%`.

### Hazard definitions tested

1. `context_plus_one_tech` — weak breadth OR weak market20, plus at least one technical hazard.
2. `context_plus_two_tech` — weak breadth OR weak market20, plus at least two technical hazards.
3. `weak_breadth_plus_one_tech` — weak breadth plus at least one technical hazard.
4. `double_context_plus_one_tech` — weak breadth AND weak market20, plus at least one technical hazard.

Technical hazards are weak RS20, extended breakout, or tight overhead.

### Staged protection grid

- Probe fraction: 30%, 35%, 40%, 45%.
- Confirmation day: session 1 only.
- Confirmation:
  - Close >= entry.
  - MFE >= +2%.
  - Close >= entry AND MFE >= +2%.
- If not confirmed:
  - keep the probe, or
  - exit the probe.

Total configurations: **96**.

## Validation protocol

Selection uses only:

- 2023.
- 2024.

The final research period 2025-01-01 through 2026-02-28 is **algorithmically not used in selection**. It is not described as a pristine unseen holdout because it has already been observed during the broader research program.

A configuration must satisfy all of the following in both 2023 and 2024:

- Ending wealth >= 98% of v3.2.
- Relative max-drawdown reduction >= 10%.
- Active-week >=2% hit-rate >= 95% of v3.2.
- Hazard subset <= 35% of signals.
- At least 12 trades.

## Exact v3.2 baseline reproduced by this engine

### 2023

- Trades: 20.
- Return: **+38.7835%**.
- Max drawdown: **-6.4973%**.
- Active-week >=2% rate: **38.4615%**.

### 2024

- Trades: 27.
- Return: **+46.2195%**.
- Max drawdown: **-11.1657%**.
- Active-week >=2% rate: **38.4615%**.

### Final research period baseline

- Trades: 42.
- Return: **+71.0060%**.
- Max drawdown: **-6.9091%**.
- Active-week >=2% rate: **37.2093%**.

## Result

**Eligible configurations: 0 / 96.**

No configuration was selected, and therefore no v5.8 candidate was opened on the final research period.

## Hazard attribution result

The central problem was not only the staging rule. The proposed pre-entry hazard definitions were not stable enough across years.

### `context_plus_two_tech`

This definition did identify a materially weaker subset in validation:

2023 hazard subset:

- 14 signals.
- Stop rate: **42.86%**.
- Avg gross return: **+2.57%**.

2023 non-hazard subset:

- 15 signals.
- Stop rate: **13.33%**.
- Avg gross return: **+4.53%**.

2024 hazard subset:

- 9 signals.
- Stop rate: **55.56%**.
- Avg gross return: **+2.23%**.

2024 non-hazard subset:

- 22 signals.
- Stop rate: **31.82%**.
- Avg gross return: **+2.66%**.

This is directionally useful, but in 2023 the hazard share was **48.28%**, so it was not a genuinely small subset. More importantly, the resulting staged variants did not achieve the required 10% drawdown reduction in both years.

A representative near miss using 45% probe, day-1 `MFE >= 2%`, and holding an unconfirmed probe produced:

- 2023 return: **+38.5155%** vs +38.7835% baseline.
- 2023 DD: **-6.3309%** vs -6.4973% baseline.
- 2024 return: **+46.2543%** vs +46.2195% baseline.
- 2024 DD: **-10.9281%** vs -11.1657% baseline.
- Minimum wealth preservation: about **99.81%**.
- Minimum relative DD reduction: only about **2.13%**.
- Active-week >=2% preservation: **100%**.

This is notable because it preserved return extremely well, but the risk improvement was too small.

### `double_context_plus_one_tech`

This was more selective in 2023 but unstable across years:

- 2023 hazard share: **10.34%**.
- 2024 hazard share: **41.94%**.

A 35% probe / close>=entry / exit-if-unconfirmed variant improved 2024 strongly:

- 2024 return: **+47.4824%** vs +46.2195%.
- 2024 DD: **-8.1935%** vs -11.1657%.

But it worsened 2023 drawdown:

- 2023 return: **+38.8144%** vs +38.7835%.
- 2023 DD: **-6.8914%** vs -6.4973%.

So the same rule that helped the exact 2024 problem failed cross-year stability.

## Important diagnostic conclusion

v5.8 gives two useful findings:

1. **Selective staging is much less destructive to return than staging every trade.** Some variants preserved essentially 100% of v3.2 wealth and active-week behavior.
2. **The bottleneck is now hazard attribution, not position sizing.** The current simple combination of breadth, market20, RS20, breakout extension, and overhead does not isolate a small, stable failure subset across both validation years.

This means the next research version should not simply tune these thresholds more finely after seeing the results. That would risk overfitting.

## Research status

**Rejected as a replacement. Diagnostic value retained.**

v3.2 remains the reference.

## Files

- `backtest_v58_selective_hazard_gate.py`
- `results_v58_selective_hazard_gate.json`
- `DEFENSIVE_LIFT_V58.md`

## Reproducibility note

The public historical dataset contains 198 usable CSV symbols in this run. The dataset's actual maximum date is 2026-02-04 even where research-period labels extend through February 2026.

Backtest results are research evidence, not a guarantee of future performance.
