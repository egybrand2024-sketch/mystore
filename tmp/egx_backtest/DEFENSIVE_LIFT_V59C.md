# Defensive Lift v5.9C — Clearance + High Lift

**Status: Passed validation, Rejected after final research period**

## Hypothesis
Protect only DLP breakouts that combine high clearance above resistance with a high pre-breakout defensive lift.

Thresholds frozen from 2021–2022 raw DLP signals:
- Clearance >= 3.2602%
- Lift >= 5.9491%

Normal non-hazard v3.2 entries remain unchanged at 50% portfolio size.

## Grid
24 configurations:
- Probe: 30%, 35%, 40%, 45%
- Confirmation: MFE >= 2%; close >= entry; or both
- If unconfirmed: hold probe or exit probe

Strict acceptance per 2023 and 2024:
- Wealth ratio >= 98% of v3.2
- Drawdown reduction >= 10%
- Active-week >=2% rate >= 95% of v3.2
- Hazard share <= 35%

## Validation result
6/24 configurations passed the strict validation criteria.

Best validation configuration:
- Probe 30%
- Confirmation: MFE >= 2% after day 1
- If unconfirmed: exit probe

2023:
- v3.2 return +38.78%, DD -6.50%
- v5.9C return +40.48%, DD -5.54%
- DD reduction about 14.7%

2024:
- v3.2 return +46.22%, DD -11.17%
- v5.9C return +50.87%, DD -9.10%
- DD reduction about 18.5%

Minimum wealth ratio across validation years: 101.22% of baseline.
Minimum DD reduction: 14.69%.
Active-week >=2% ratio: 100% of baseline.
Hazard share: about 13–14%.

This is the first candidate in the current research chain to beat v3.2 on both return and drawdown in both 2023 and 2024 while passing the predeclared acceptance criteria.

## Final research period
Because validation passed, the final research period was opened.

v3.2 final research period:
- Return +71.01%
- DD -6.91%

v5.9C final research period:
- Return +58.38%
- DD -6.91% (slightly worse numerically)
- 43 entered trades, 19 skipped

The candidate therefore **failed to preserve the final-period right tail** and did not improve final drawdown. It is rejected as a replacement despite excellent validation performance.

## Conclusion
The underlying hazard hypothesis — high clearance + high lift — is materially stronger than previous hazard definitions, but the day-1 probe/exit implementation is not stable enough across regimes. The hazard detector is retained as a strong diagnostic lead; the trading rule is not adopted.
