# Defensive Lift v5.10B — Two-Day Hold Confirmation

Status: **Rejected / Near Miss**

## Frozen hazard detector
- Clearance >= 3.260246%
- Lift >= 5.949147%
- Thresholds frozen from 2021-2022.

## Architecture
Hazard trades start below the normal 50% v3.2 allocation. The position is never exited or reduced early. It is added back to 50% only if the day-2 close remains constructive versus entry.

## Validation grid
12 configurations. Strict acceptance required wealth >= v3.2 in both 2023 and 2024, drawdown reduction >=10% in both years, and active-week >=2% ratio >=95%.

## Best near miss
- Initial fraction: 40%
- Day-2 close confirmation: >= entry
- 2023: return +39.1391% vs v3.2 +38.7835%; max DD -6.0200% vs -6.4973%.
- 2024: return +46.9633% vs v3.2 +46.2195%; max DD -10.6964% vs -11.1657%.
- Minimum wealth ratio: 1.00256.
- Minimum drawdown reduction: 4.203%.
- Active >=2% weekly ratio preserved at 1.0.

## Decision
Rejected because risk reduction did not reach the frozen 10% requirement in both validation years. The final research period was not opened because there was no strict eligible configuration.
