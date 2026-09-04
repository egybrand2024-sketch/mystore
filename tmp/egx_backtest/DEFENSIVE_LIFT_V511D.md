# Defensive Lift v5.11D — Asymmetric Winner Pyramid

Status: **Validation pass / final fail**.

Frozen v5.9C hazard detector. Strict validation requires higher return and lower absolute max drawdown than v5.10C in both 2023 and 2024 while preserving active-week >=2% rate. Final must then beat v3.2 on return and drawdown.

Grid: 81 configurations. Strict validation passes: 27.

Selected configuration: initial 30%, day-1 MFE >=1% and close >= entry adds to 50%; if by day 2 cumulative MFE >=2% and close remains >= entry, pyramid to 65% without leverage.

Validation:
- 2023: +40.8536%, DD -5.5428% versus v5.10C +40.0376%, DD -5.7814%.
- 2024: +49.3027%, DD -10.2329% versus v5.10C +48.0007%, DD -10.4646%.

Final research period:
- v5.11D: +69.1555%, DD -6.9122%.
- v3.2: +71.0060%, DD -6.9091%.

Return is lower by ~1.851 percentage points and drawdown is fractionally worse. Strict final dominance fails. Frozen as rejected final candidate.
