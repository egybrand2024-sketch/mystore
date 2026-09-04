# Defensive Lift v5.9B — Clearance + Weak Market20

**Status: Rejected / Near Miss**

## Hypothesis
Protect only DLP breakouts that are unusually extended above resistance while the 20-session market context is weak.

Thresholds frozen from 2021–2022 raw DLP signals:
- Clearance >= 3.2602%
- Market20 <= -0.2638%

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

## Hazard profile
- 2023: 1 hazard signal; 1 fast stop; fast-stop rate 100%
- 2024: 6 hazard signals; 2 fast stops; fast-stop rate 33.3%

## Best near miss
Probe 35%, confirmation `MFE >= 2%`, hold probe if unconfirmed.

2023:
- v3.2 return +38.78%, DD -6.50%
- v5.9B return +39.85%, DD -6.50%

2024:
- v3.2 return +46.22%, DD -11.17%
- v5.9B return +48.16%, DD -10.46%

The candidate improved wealth in both validation years, but 2023 drawdown was unchanged. Therefore the minimum cross-year DD reduction was effectively 0%, and 0/24 configurations were strictly eligible.

## Conclusion
Weak Market20 helps isolate some bad trades, especially in 2024, but the rule is too asymmetric across years to be a stable hazard gate. It is not a replacement for v3.2.
