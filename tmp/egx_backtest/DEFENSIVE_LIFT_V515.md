# Defensive Lift v5.15 — Ensemble Surgical Gate

## Status
NO STRICT CHAMPION, but closest pre-v5.17 frontier result.

## Purpose
Combine multiple high-precision pre-entry loss filters with OR logic so only a tiny set of historically loss-prone trades receives minimal allocation.

## Search
- 468 primitive thresholds from 2021–2022 quantiles.
- 24,734 candidate two-condition atoms.
- 36 highest-value atoms retained.
- 1,230 one/two/three-atom ensembles.
- 11,070 sizing configurations.
- Historical optimization across already-observed 2023–2026 outcomes; not pristine out-of-sample.

## Best ensemble
Atom 1:
- rs20 >= 0.0734005983 (q75), AND
- market5_ret >= 0.0085434518 (q70).

Atom 2:
- lift >= 0.0596590235 (q75), AND
- gap <= approximately 0 (q15).

Protected allocation: 5%.

The ensemble flagged only stops in the observed periods:
- 2023: SMFR, EFID.
- 2024: UNIP, CIEB, ORWE.
- Final: RAKT, SNFC.

Results:
- 2023: +45.23%, DD -4.35%.
- 2024: +56.42%, DD -6.98%.
- Final: +78.70%, DD -6.07%.

This beat the six-version return frontier in all three periods and beat the DD frontier in 2024, but missed the DD frontier by ~0.04 percentage point in 2023 and ~0.12 point in the final period. Therefore it remained rejected under the frozen strict definition.
