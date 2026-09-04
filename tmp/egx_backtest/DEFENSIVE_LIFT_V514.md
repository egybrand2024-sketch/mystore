# Defensive Lift v5.14 — Staged Surgical Refill

## Status
NO STRICT CHAMPION.

## Purpose
Preserve the surgical-gate idea but refill protected trades after early positive confirmation, attempting to recover validation return without giving back risk control.

## Search
- 100 surgical rules.
- 144 staged-refill configurations per rule.
- 14,400 total configurations.
- Historical optimization across already-observed 2023–2026 research periods; not pristine out-of-sample.

## Best near miss
Pre-entry rule:
- slope10 >= 0.0043443984 (2021–22 q75), AND
- pre60_ret <= -0.1186046360 (2021–22 q15).

Sizing:
- initial 10%,
- day-1 refill toward 45% after positive confirmation,
- no final pyramid beyond 50% in the selected configuration.

Results:
- 2023: +38.78%, DD -6.50% (effectively baseline; no flagged trades).
- 2024: +47.83%, DD -10.19%.
- Final: +74.50%, DD -6.91%.

It raised final return materially above v3.2 but did not improve final drawdown and remained below the six-version frontier in validation. Rejected.
