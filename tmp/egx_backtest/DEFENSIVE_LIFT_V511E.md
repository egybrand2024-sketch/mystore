# Defensive Lift v5.11E — Adaptive Hybrid: Selective Protection + Pyramid

Status: **Validation pass / final fail**.

Frozen v5.9C hazard detector. Additional severe/context thresholds are frozen from 2021-2022. Strict validation requires higher return and lower absolute max drawdown than v5.10C in both 2023 and 2024 while preserving active-week >=2% rate. Final must then beat v3.2 on return and drawdown.

Grid: 144 configurations. Strict validation passes: 24.

Selected configuration: q90 severe tier; weak context by Market20; protected hazard entries start 30% with temporary 3% first-session stop and relax after MFE +1.5%; confirmed day-1 winners add to 50%; qualifying day-2 winners may pyramid to 55%.

Validation:
- 2023: +42.9218%, DD -5.1135% versus v5.10C +40.0376%, DD -5.7814%.
- 2024: +50.6874%, DD -10.2329% versus v5.10C +48.0007%, DD -10.4646%.

This is the strongest validation result of the five tests.

Final research period:
- v5.11E: +69.1555%, DD -6.9122%.
- v3.2: +71.0060%, DD -6.9091%.

Return is lower by ~1.851 percentage points and drawdown is fractionally worse, so strict final dominance fails. Frozen as rejected final candidate despite strong validation.
