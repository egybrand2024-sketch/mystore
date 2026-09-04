# Defensive Lift v5.10C — Progressive 2-Step Add

Status: **Rejected / Near Miss**

## Frozen hazard detector
- Clearance >= 3.260246%
- Lift >= 5.949147%
- Thresholds frozen from 2021-2022.

## Architecture
Hazard trades enter smaller, add partially after day-1 MFE confirmation, then reach the full 50% allocation only if day-2 close remains constructive. No early exit or position reduction is allowed.

## Validation grid
54 configurations. Strict acceptance required wealth >= v3.2 in both 2023 and 2024, drawdown reduction >=10% in both years, and active-week >=2% ratio >=95%.

## Best near miss
- Start fraction: 35%
- Day-1 partial target fraction: 47.5%
- Day-1 MFE confirmation: +2%
- Day-2 close confirmation: >= entry
- 2023: return +40.0376% vs v3.2 +38.7835%; max DD -5.7814% vs -6.4973%.
- 2024: return +48.0007% vs v3.2 +46.2195%; max DD -10.4646% vs -11.1657%.
- Minimum wealth ratio: 1.00904.
- Minimum drawdown reduction: 6.279%.
- Active >=2% weekly ratio preserved at 1.0.

## Decision
Rejected because risk reduction still did not reach the frozen 10% requirement in both validation years. The final research period was not opened because there was no strict eligible configuration.

## Interpretation
Of the three no-early-exit protection architectures, progressive adding was the strongest. It increased validation wealth in both years and reduced drawdown more than v5.10A/B, but the protection remained too weak to satisfy the predeclared risk target.
