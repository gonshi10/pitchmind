# PitchMind schema (DuckDB)

All data is **La Liga 2015/2016** (`competition_id = 11`, `season_id = 27`). Every query
**must** filter on both, must be a read-only `SELECT`, and must include a `LIMIT`.

Pitch convention (StatsBomb): coordinates are on a **120 × 80** pitch. The attacking
direction is toward **x = 120** (the opponent goal), so a forward action *increases* `x`.
`y` runs across the pitch (0 = left touchline, 80 = right). The **final third** is `x >= 80`;
the **penalty box** is `x >= 102 AND y BETWEEN 18 AND 62`.

Prefer the **marts** (`mart_player_season`, `mart_shots`) for aggregate questions — they are
pre-computed and carry the canonical metric definitions. Use the event views for anything the
marts don't cover.

## Marts (use these first)

### `mart_player_season` — one row per player, season totals
- `player_id`, `player_name`, `team_name`, `team_id`, `competition_id`, `season_id`
- `matches_played` — distinct matches the player appears in
- `shots`, `goals`, `xg` — shot count, goals scored, total StatsBomb xG
- `passes`, `passes_completed` — total passes, completed passes (outcome is NULL = completed)
- `progressive_passes` — completed passes advancing ≥ 10 toward goal (`pass_end_x - location_x >= 10`)
- `progressive_passes_under_pressure` — the above, while `under_pressure`
- `assists` — passes flagged `pass_goal_assist`
- `progressive_carries` — carries advancing ≥ 10 toward goal (`carry_end_x - location_x >= 10`)
- `progressive_carries_under_pressure` — the above, while `under_pressure`
- `ball_progressions` — `progressive_passes + progressive_carries`
- `ball_progressions_under_pressure` — under-pressure sum of the two

### `mart_shots` — one row per shot (backs the shot-map viz)
- `shot_id`, `match_id`, `player`, `player_id`, `team`, `team_id`
- `x`, `y` — shot location on the 120 × 80 pitch
- `xg` — StatsBomb expected-goals value
- `shot_outcome` (e.g. 'Goal', 'Saved', 'Off T', 'Blocked'), `shot_type`, `shot_body_part`
- `under_pressure` (bool), `is_goal` (bool, `shot_outcome = 'Goal'`)

## Event views (raw, one row per event)

Every view shares: `id`, `match_id`, `competition_id`, `season_id`, `period`, `minute`,
`second`, `team`, `team_id`, `player`, `player_id`, `position`, `location_x`, `location_y`,
`under_pressure`, `play_pattern`.

- **`v_shots`** — `shot_statsbomb_xg`, `shot_outcome`, `shot_type`, `shot_body_part`,
  `shot_technique`, `shot_end_x`, `shot_end_y`, `shot_end_z`, `shot_first_time`,
  `shot_key_pass_id`. A goal is `shot_outcome = 'Goal'`.
- **`v_passes`** — `pass_recipient`, `pass_recipient_id`, `pass_length`, `pass_angle`,
  `pass_height`, `pass_end_x`, `pass_end_y`, `pass_outcome` (NULL = completed),
  `pass_type`, `pass_body_part`, `pass_switch`, `pass_cross`, `pass_cut_back`,
  `pass_shot_assist`, `pass_goal_assist`.
- **`v_carries`** — `carry_end_x`, `carry_end_y`.
- **`v_pressures`** — `counterpress`.
- **`v_dribbles`** — `dribble_outcome` ('Complete' / 'Incomplete').
- **`v_duels`** — `duel_type`, `duel_outcome`.
- **`v_interceptions`** — `interception_outcome`.
- **`v_ball_receipts`** — `ball_receipt_outcome`.

## Entity tables (for joins / disambiguation; resolution is done before SQL)
- **`players`** — `player_id`, `player_name`, `team_name`, `team_id` (player's main team).
- **`teams`** — `team_id`, `team_name`.
- **`aliases`** — `kind` ('player'|'team'), `entity_id`, `name`, `alias`, `alias_norm`.

When the plan has already resolved an entity to an id, filter by that id
(`player_id = ...`, `team_id = ...`) rather than matching on the name string.
