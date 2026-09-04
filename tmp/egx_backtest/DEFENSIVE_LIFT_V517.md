# Defensive Lift v5.17 — Third-Atom Final DD Fix

## Status
STRICT HISTORICAL CHAMPION under the frozen six-version frontier definition.

## Critical caveat
This version is explicitly optimized against already-observed 2023, 2024 and 2025–Feb 2026 outcomes, including the known 2025-09-08 to 2025-09-29 drawdown. It is NOT pristine out-of-sample evidence and must not be presented as a validated live trading edge. It is a historical research champion only.

## Frozen base ensemble inherited from v5.15/v5.16
Atom 1:
- rs20 >= 0.0734005983 (2021–22 q75), AND
- market5_ret >= 0.0085434518 (q70).

Atom 2:
- lift >= 0.0596590235 (q75), AND
- gap <= approximately 0 (q15).

These conditions are OR'ed: a trade matching either atom is rejected in the selected historical champion path.

## Third atom added in v5.17
- lift <= 0.0476414785 (2021–22 q30), AND
- compression_ratio >= 1.1391181814 (q85).

This third atom was selected specifically to address the remaining already-observed final-period drawdown. It captured HELI entered 2025-09-14, which stopped on 2025-09-16, plus several additional historical timeouts/stops.

## Search
- 784 candidate third atoms met the drawdown-targeting filter.
- Top 400 tested with the frozen base ensemble.
- 346 configurations passed the strict historical frontier test.

## Champion results
Six-version frontier to beat:
- 2023: return > +42.9218%, DD better than -4.3087%.
- 2024: return > +50.6874%, DD better than -8.0113%.
- Final: return > +71.0060%, DD better than -5.9472%.

v5.17 historical champion:
- 2023: +43.7338%, DD -2.8795%.
- 2024: +61.6034%, DD -6.5250%.
- Final research period: +86.1628%, DD -4.8753%.

Edges over the six-version frontier:
- 2023: +0.8120 pp return, +1.4291 pp DD improvement.
- 2024: +10.9159 pp return, +1.4863 pp DD improvement.
- Final: +15.1568 pp return, +1.0720 pp DD improvement.

## Interpretation
This is the first research version to exceed BOTH the strongest historical return frontier and the strongest historical DD frontier in all three observed periods under the same rule set.

However, because the rule itself was constructed after observing those periods, v5.17 should now be frozen and subjected to a genuinely new forward/out-of-sample period before any claim of superiority over v3.2 for live use.
