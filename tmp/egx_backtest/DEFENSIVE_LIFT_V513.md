# Defensive Lift v5.13 — Surgical Pre-Entry Gate

## Status
NO STRICT CHAMPION.

## Purpose
Target a very small number of historically harmful trades using causal pre-entry features while preserving normal v3.2 sizing for the rest.

## Search
- 198 stocks, 170 DLP signals.
- 468 primitive threshold rules derived from 2021–2022 quantiles.
- 400 shortlisted single/pair rules.
- 3,200 sizing configurations.
- Historical selection used 2023, 2024 and the already-observed 2025–Feb 2026 research period; therefore this is not pristine out-of-sample evidence.

## Best near miss
Rule: compression_ratio >= 1.1391181814 (2021–22 q85), protected fraction 10%.

- 2023: +37.09%, DD -5.00%.
- 2024: +42.19%, DD -7.10%.
- Final research period: +71.89%, DD -5.63%.

The final period simultaneously exceeded v3.2 return and v5.1 drawdown, but the same rule materially reduced 2023/2024 return, so it was rejected as a universal replacement.

## Frozen interpretation
Compression is useful as a regime-sensitive risk feature, not a stable standalone universal gate.
