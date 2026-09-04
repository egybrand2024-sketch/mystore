# Defensive Lift v5.9A — Clearance + Low Resistance Touches

**Status: Rejected / Near Miss**

## Hypothesis
Protect only DLP breakouts that are unusually extended above resistance and came from a base with relatively few resistance touches.

Hazard thresholds are frozen from 2021–2022 raw DLP signals:
- Clearance >= 3.2602%
- Resistance touches <= 2

Normal non-hazard v3.2 entries remain unchanged at 50% portfolio size. Hazard trades are staged using a probe, with add-on/hold logic evaluated after day 1.

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

## Hazard profile
- 2023: 3 raw hazard signals, 2 fast stops, 1 target; fast-stop rate 66.7%
- 2024: 3 raw hazard signals, 2 fast stops, 1 target; fast-stop rate 66.7%

## Best near miss
Probe 35%, confirmation `close >= entry`, hold probe if unconfirmed.

2023:
- v3.2 return +38.78%, DD -6.50%
- v5.9A return +40.92%, DD -5.78%

2024:
- v3.2 return +46.22%, DD -11.17%
- v5.9A return +47.50%, DD -11.17%

The configuration improved wealth in both years and reduced 2023 DD, but **did not reduce 2024 drawdown at all**, so the minimum cross-year DD reduction was effectively 0%. Therefore 0/24 configurations were strictly eligible.

## Conclusion
The hazard definition is directionally useful but too sparse and does not touch the dominant 2024 drawdown path reliably enough. It is not a replacement for v3.2.
