# Defensive Lift — v5.6 Early Path Behavior

## Status

**Rejected Research Version**

`v5.6` tested whether the first 1–3 sessions after a valid v2 DLP breakout can identify failing trades early enough to reduce portfolio drawdown without sacrificing the right tail of +12% winners.

The version is isolated on branch:

`tmp-egx-defensive-lift-v56-20260904`

It does not modify the frozen `v3.2` documentation or rules.

## Frozen baseline

- Entry: frozen v2 DLP
- Target: +12%
- Stop: -4.5%
- Maximum holding: 7 sessions
- Maximum simultaneous positions: 2
- Nominal slot: 50% of equity
- Round-trip friction sensitivity: 0.50%
- Same-day target/stop ambiguity: conservative stop-first
- Candidate ranking: v3.2 liquidity ranking

Exact v3.2 baseline reproduced:

### 2023
- Return: +38.7835%
- Max Drawdown: -6.4973%
- Trades: 20

### 2024
- Return: +46.2195%
- Max Drawdown: -11.1657%
- Trades: 27

### Final research period 2025–2026-02
- Return: +71.0060%
- Max Drawdown: -6.9091%
- Trades: 42

The final research period was not used for rule selection. It is not described as pristine unseen because it has been observed in prior research versions.

## Hypothesis

Targets and stops show visibly different early paths. The research question was whether a simple exit rule, based only on information available after day 1, 2, or 3, could cut failed breakouts before the full -4.5% stop.

Tested state variables:

- close return from breakout entry after day 1 / 2 / 3
- maximum favorable excursion (MFE) observed up to that checkpoint
- whether close remains below the breakout close

Rules were intentionally simple and interpretable. No ML model was used.

## Early-path diagnostics

The diagnostic pattern is real and visually strong.

### 2023
Target trades:
- Day 1 average close: +4.13%
- Day 2: +5.05%
- Day 3: +6.88%
- By day 3, 0% of target trades closed below entry.

Stop trades:
- Day 1 average close: -1.55%
- Day 2: -1.59%
- Day 3: -0.85%
- 75% of stop trades closed below entry on day 1.

### 2024
Target trades:
- Day 1 average close: +4.58%
- Day 2: +9.46%
- Day 3: +13.71%

Stop trades:
- Day 1 average close: -0.65%
- Day 2: -2.18%
- Day 3: -3.01%
- 66.7% of stop trades closed below entry on day 1.
- 75% were below entry by day 2 and day 3.

This confirms that successful DLP trades often accelerate rapidly, while failed trades tend to remain weak or deteriorate.

## Grid

45 valid rule configurations were tested from combinations of:

- Check day: 1, 2, 3
- Close thresholds: -1%, -2%, -3%
- MFE thresholds: 0%, +1%, +2%
- Modes:
  - close-only
  - close + low-MFE
  - below-breakout-close

Acceptance requirements in both 2023 and 2024:

- ending wealth >= 98% of v3.2
- Max Drawdown reduction >= 10%
- active-week >= +2% hit-rate >= 95% of v3.2
- minimum 12 trades

## Result

**Eligible configurations: 0 / 45**

No rule satisfied all three preservation/risk conditions in both validation years.

Several rules improved return slightly while preserving weekly behavior, but the 2024 Max Drawdown remained effectively unchanged at about -11.17%.

Example near miss:

- Check: day 1
- Rule: close <= -1% AND MFE <= 0%

2023:
- Return unchanged at +38.78%
- Max DD unchanged at -6.50%
- Early exits: 0

2024:
- Return improved to about +48.22%
- Max DD remained about -11.17%
- Early exits: 1

The improvement in return did not solve the drawdown problem.

## Main finding

The central failure mechanism is now clearer:

**Close-based early exits often occur too late to protect against the drawdown-driving DLP failures.**

The simulator checks the structural -4.5% stop intraday before a day-end early-failure rule. A trade can hit the stop during the session even if its closing path later gives a useful warning. Therefore, a day-1/day-2/day-3 close rule cannot prevent many of the losses that created the 2024 drawdown.

This explains why the path diagnostics can show a strong separation between winners and losers while the portfolio Max Drawdown does not improve.

## Research interpretation

`v5.6` rejects the idea that a simple end-of-day emergency exit is sufficient.

However, the diagnostic itself is valuable:

- target trades show strong positive acceleration early
- stop trades show weak MFE and negative closes
- the distinction is visible, but often only after intraday stop risk has already been realized

Therefore the next useful direction is not a tighter close-based stop. A later version should investigate whether the early path can be used to **change the entry architecture before full risk is committed**, for example:

- staged exposure after breakout
- confirmation-based second tranche
- initial probe with add-on only after continuation

Any such change must be a new version and must be judged against the same wealth, DD, and right-tail preservation constraints.

## Files

- `backtest_v56_early_path_behavior.py`
- `results_v56_early_path_behavior.json`
- `DEFENSIVE_LIFT_V56.md`

## Final status

**Rejected as replacement for v3.2.**

`v3.2` remains the High-Return Research Reference.