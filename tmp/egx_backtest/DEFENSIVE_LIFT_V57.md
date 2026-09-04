# Defensive Lift v5.7 — Staged Probe + Add-on

## Status

**Rejected Research Version** — 0 / 64 configurations met the validation requirements in both 2023 and 2024.

`v3.2` remains the High-Return Research Reference.

## Hypothesis

v5.6 showed that losing breakouts often reveal weak early path behavior during the first 1–3 sessions, but end-of-day emergency exits frequently occur too late to reduce the main drawdown. v5.7 therefore tested whether the system could reduce loss severity by entering a smaller **probe** first and restoring the full 50% allocation only after early continuation was observed.

The objective was not to permanently shrink risk. Maximum size per idea remained 50% of equity.

## Frozen components

- Entry pattern: frozen v2 DLP.
- Target: +12% from the original breakout entry anchor.
- Stop: -4.5% from the original breakout entry anchor.
- Horizon: 7 sessions.
- Max simultaneous ideas: 2.
- Maximum full size per idea: 50%.
- Round-trip friction sensitivity: 0.5%.
- Ranking: v3.2 liquidity ranking.

## Staged mechanism

Probe sizes tested:

- 15%
- 20%
- 25%
- 30%

Add-on decision after:

- session 1
- session 2

Continuation tests:

1. Close >= original entry.
2. Close >= original entry +1%.
3. MFE >= +2%.
4. Close >= entry AND MFE >= +2%.

If continuation failed, two actions were tested:

- keep only the probe until the normal exit;
- exit the probe early.

Total grid: **4 × 2 × 4 × 2 = 64 configurations**.

## Validation protocol

Selection used 2023 and 2024 only.

A configuration had to satisfy in **both** validation years:

- ending wealth >= 98% of v3.2;
- relative Max Drawdown reduction >= 10%;
- active-week >= +2% rate >= 95% of v3.2;
- at least 12 trades.

The final research period 2025–Feb 2026 was not used for selection. Because no configuration qualified, no v5.7 final candidate was opened.

## Exact v3.2 baselines reproduced

### 2023

- 20 trades.
- Ending equity: 138,783.53.
- Total return: +38.7835%.
- Max Drawdown: -6.4973%.
- Active-week >= +2% rate: 38.4615%.

### 2024

- 27 trades.
- Ending equity: 146,219.46.
- Total return: +46.2195%.
- Max Drawdown: -11.1657%.
- Active-week >= +2% rate: 38.4615%.

### Final research baseline

- 42 trades.
- Ending equity: 171,006.01.
- Total return: +71.0060%.
- Max Drawdown: -6.9091%.

## Result

**Eligible configurations: 0 / 64.**

The strongest near-miss used:

- Probe: 30%.
- Add-on check: session 1.
- Confirmation: MFE >= +2%.
- If unconfirmed: keep the probe rather than exit it.

### Near-miss 2023

- Return: +31.6616% vs +38.7835% v3.2.
- Max Drawdown: -4.1725% vs -6.4973%.
- Added to full size on 8 trades.
- Active-week >= +2% rate: 38.4615% — equal to baseline.

### Near-miss 2024

- Return: +33.7085% vs +46.2195% v3.2.
- Max Drawdown: -9.5755% vs -11.1657%.
- Added to full size on 13 trades.
- Active-week >= +2% rate: 34.6154% vs 38.4615% baseline.

Across validation, minimum wealth ratio was only about **91.44%**, while minimum relative drawdown reduction was about **14.24%**. The drawdown objective was achieved, but too much right-tail return was lost.

## Interpretation

v5.7 confirms an important trade-off:

> Starting smaller before confirmation does reduce drawdown, but DLP winners often deliver enough of their edge immediately that delaying full exposure sacrifices too much upside.

The problem is not that staged entry cannot reduce risk; it can. The problem is that the reduction in early capital exposure also reduces participation in the exact right-tail moves that make v3.2 profitable.

This means the simple sequence **small probe → wait 1–2 sessions → add to 50%** is not a replacement for v3.2 under the current evidence.

## Research conclusion

v5.6 showed early path contains information. v5.7 showed that using that information by universally staging entry is too expensive in foregone upside.

A future version should therefore avoid staging every DLP trade. If the research continues, the more promising direction is to identify a very small subset of entries where full immediate exposure is specifically dangerous, while leaving normal v3.2 entries at 50% from the start.

No result here is a guarantee of future performance.
