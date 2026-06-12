---
description: Run the full ETL chain for La Liga 2015/16 and report row counts
allowed-tools: Bash(pitchmind:*), Bash(python -m pitchmind.cli:*)
---

Run the complete PitchMind ETL pipeline for La Liga 2015/16, in order, and report the
outcome of each step plus final row counts.

Steps (each is idempotent and re-runnable):
1. `pitchmind etl download`
2. `pitchmind etl flatten`
3. `pitchmind etl load-duckdb`
4. `pitchmind etl entity-index`
5. `pitchmind etl marts`

After it completes, verify the build is sane:
- `v_shots` has rows (`SELECT count(*) FROM v_shots`)
- `mart_player_season` is populated
- the entity index (`players`, `teams`, `aliases`) is non-empty

Report any step that failed with its error, and the final counts. Do not proceed past a
failing step — fix the ETL, not the symptom.
