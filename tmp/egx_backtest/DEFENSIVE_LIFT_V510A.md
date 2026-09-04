# Defensive Lift v5.10A — Soft 1-Day Momentum Hold

Status: **Rejected / Near Miss**

## Frozen hazard detector
- Clearance >= 3.260246%
- Lift >= 5.949147%
- Thresholds frozen from 2021-2022.

## Architecture
Hazard trades start slightly below the normal 50% v3.2 allocation. If day-1 MFE confirms strength, the position is added back toward the frozen 50% budget. If not confirmed, the smaller position is held. No early exit or reduction is allowed.

## Validation grid
16 configurations. Strict acceptance required wealth >= v3.2 in both 2023 and 2024, drawdown reduction >=10% in both years, and active-week >=2% ratio >=95%.

## Best near miss
- Initial fraction: 40%
- Day-1 MFE confirmation: +2%
- 2023: return +39.6775% vs v3.2 +38.7835%; max DD -6.0200% vs -6.4973%.
- 2024: return +47.5416% vs v3.2 +46.2195%; max DD -10.6964% vs -11.1657%.
- Minimum wealth ratio: 1.00644.
- Minimum drawdown reduction: 4.203%.
- Active >=2% weekly ratio preserved at 1.0.

## Decision
Rejected because risk reduction did not reach the frozen 10% requirement in both validation years. The final research period was not opened because there was no strict eligible configuration.
