# Metric glossary — football language → computation

These definitions are canonical. Where a metric is pre-computed in `mart_player_season`,
use the mart column; the formula is given so ad-hoc SQL over the event views matches.

- **xG (expected goals)** — `shot_statsbomb_xg` per shot; a player/team total is its sum.
  In the marts, `mart_player_season.xg` and `mart_shots.xg`.

- **Goal** — a shot with `shot_outcome = 'Goal'`. (Own goals are separate event types and are
  *not* in `v_shots`.) `mart_player_season.goals`.

- **Completed pass** — a pass with `pass_outcome IS NULL`. Incomplete/out/offside passes carry
  a non-null `pass_outcome`. `mart_player_season.passes_completed`.

- **Pass completion %** — `passes_completed / passes * 100`.

- **Under pressure** — the StatsBomb `under_pressure` flag (boolean) on the event. "X under
  pressure" means filter `under_pressure = TRUE`.

- **Final third** — pitch zone `x >= 80` (attacking toward x = 120).

- **Penalty box / "into the box"** — `x >= 102 AND y BETWEEN 18 AND 62`. A *pass into the box*
  is a completed pass whose **end** location is in the box: `pass_end_x >= 102 AND pass_end_y
  BETWEEN 18 AND 62`.

- **Progressive pass** — a completed pass that advances the ball **≥ 10 toward the opponent
  goal**: `pass_outcome IS NULL AND (pass_end_x - location_x) >= 10`. Pre-computed as
  `mart_player_season.progressive_passes`.

- **Progressive carry** — a carry advancing the ball **≥ 10 toward goal**:
  `(carry_end_x - location_x) >= 10`. `mart_player_season.progressive_carries`.

- **Ball progression** — progressive passes **plus** progressive carries.
  `mart_player_season.ball_progressions`. The **under-pressure** variant adds
  `under_pressure = TRUE` to each and lives in `ball_progressions_under_pressure`.
  This is the metric for "who progressed the ball most under pressure".

- **Assist** — a pass flagged `pass_goal_assist` (leads directly to a goal).
  `mart_player_season.assists`.

- **Shot-creating pass / key pass** — a pass flagged `pass_shot_assist` (leads to a shot).

- **Field tilt** — share of final-third possession between the two teams; approximate with a
  team's final-third passes (`x >= 80`) as a share of both teams' final-third passes in a match.

- **PPDA (passes allowed per defensive action)** — opponent passes in their build-up zone
  divided by the defending team's defensive actions (pressures + tackles + interceptions) in
  that zone. A lower PPDA = more aggressive pressing. (Not pre-materialized; compute from
  `v_passes`, `v_pressures`, `v_duels`, `v_interceptions` if asked.)

- **Per-90** — a count divided by minutes played, ×90. Minutes are **not** in Phase 1; use
  `matches_played` for context and state the caveat rather than inventing per-90 values.

When a question uses a fuzzy phrase ("dangerous passes", "carried it forward a lot", "busy in
the final third"), map it to the closest concrete metric above and say which one you used.
