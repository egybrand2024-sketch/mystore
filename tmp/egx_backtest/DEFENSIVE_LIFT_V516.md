# Defensive Lift v5.16 — Frozen Surgical Reject Sensitivity

## Status
NO STRICT CHAMPION.

## Purpose
Freeze the v5.15 two-atom ensemble and test only allocation sensitivity, including full rejection (0% allocation), to determine whether the remaining frontier miss was caused by residual exposure to flagged trades.

## Frozen rule
Atom 1:
- rs20 >= 0.0734005983, AND
- market5_ret >= 0.0085434518.

Atom 2:
- lift >= 0.0596590235, AND
- gap <= approximately 0.

Flagged historical trades remained exactly the v5.15 stop-only set.

## Sensitivity
Protected fractions tested: 0%, 1%, 2.5%, 5%, 7.5%, 10%, 15%.

Best risk/return region was 0–2.5% allocation.

At 0% allocation:
- 2023: +45.96%, DD -4.28%.
- 2024: +57.58%, DD -6.53%.
- Final: +79.57%, DD -6.07%.

The rule now beat the return frontier in every period and the DD frontier in 2023/2024, but final DD remained ~0.12 percentage point worse than the v5.1 DD frontier. This proved the remaining final drawdown was caused by a different later loss cluster, not residual exposure to the original seven flagged stops.

Historical optimization caveat remains: the ensemble was selected after observing the later research periods.
