"""Materialized metric marts.

Pre-aggregated tables so most questions hit a mart instead of scanning raw events, and
so fuzzy football metrics (progressive passes/carries, under-pressure progression) have a
single, consistent definition shared with the glossary.

Pitch convention (StatsBomb): 120 x 80, the attacking direction is toward x = 120, so a
forward action increases ``location_x``. "Progressive" here = a completed action that
advances the ball >= 10 units toward the opponent goal. "Final third" = x >= 80.
"""

from __future__ import annotations

import duckdb

from .. import config

PROGRESSIVE_THRESHOLD = 10  # units of forward (toward-goal) advance


def build(con: duckdb.DuckDBPyConnection | None = None) -> dict[str, int]:
    """Create ``mart_shots`` and ``mart_player_season``."""
    own = con is None
    if con is None:
        con = duckdb.connect(str(config.DB_PATH), read_only=False)

    try:
        # Per-shot table backing the shot-map viz.
        con.execute("DROP TABLE IF EXISTS mart_shots")
        con.execute(
            """
            CREATE TABLE mart_shots AS
            SELECT
                id AS shot_id, match_id, competition_id, season_id,
                player, player_id, team, team_id,
                location_x AS x, location_y AS y,
                shot_statsbomb_xg AS xg,
                shot_outcome, shot_type, shot_body_part, under_pressure,
                (shot_outcome = 'Goal') AS is_goal
            FROM v_shots
            """
        )

        # Per-player season aggregate.
        thr = PROGRESSIVE_THRESHOLD
        con.execute("DROP TABLE IF EXISTS mart_player_season")
        con.execute(
            f"""
            CREATE TABLE mart_player_season AS
            WITH shots AS (
                SELECT player_id,
                       count(*) AS shots,
                       sum(CASE WHEN shot_outcome = 'Goal' THEN 1 ELSE 0 END) AS goals,
                       sum(shot_statsbomb_xg) AS xg
                FROM v_shots GROUP BY player_id
            ),
            passes AS (
                SELECT player_id,
                       count(*) AS passes,
                       sum(CASE WHEN pass_outcome IS NULL THEN 1 ELSE 0 END)
                           AS passes_completed,
                       sum(CASE WHEN pass_outcome IS NULL
                                 AND (pass_end_x - location_x) >= {thr}
                                THEN 1 ELSE 0 END) AS progressive_passes,
                       sum(CASE WHEN pass_outcome IS NULL
                                 AND (pass_end_x - location_x) >= {thr}
                                 AND under_pressure
                                THEN 1 ELSE 0 END)
                           AS progressive_passes_under_pressure,
                       sum(CASE WHEN pass_goal_assist THEN 1 ELSE 0 END) AS assists
                FROM v_passes GROUP BY player_id
            ),
            carries AS (
                SELECT player_id,
                       sum(CASE WHEN (carry_end_x - location_x) >= {thr}
                                THEN 1 ELSE 0 END) AS progressive_carries,
                       sum(CASE WHEN (carry_end_x - location_x) >= {thr}
                                 AND under_pressure
                                THEN 1 ELSE 0 END)
                           AS progressive_carries_under_pressure
                FROM v_carries GROUP BY player_id
            ),
            appearances AS (
                SELECT player_id, count(DISTINCT match_id) AS matches_played
                FROM events WHERE player_id IS NOT NULL GROUP BY player_id
            )
            SELECT
                p.player_id, p.player_name, p.team_name, p.team_id,
                {config.TARGET.competition_id} AS competition_id,
                {config.TARGET.season_id} AS season_id,
                a.matches_played,
                COALESCE(s.shots, 0) AS shots,
                COALESCE(s.goals, 0) AS goals,
                COALESCE(s.xg, 0.0) AS xg,
                COALESCE(ps.passes, 0) AS passes,
                COALESCE(ps.passes_completed, 0) AS passes_completed,
                COALESCE(ps.progressive_passes, 0) AS progressive_passes,
                COALESCE(ps.progressive_passes_under_pressure, 0)
                    AS progressive_passes_under_pressure,
                COALESCE(ps.assists, 0) AS assists,
                COALESCE(c.progressive_carries, 0) AS progressive_carries,
                COALESCE(c.progressive_carries_under_pressure, 0)
                    AS progressive_carries_under_pressure,
                (COALESCE(ps.progressive_passes, 0)
                    + COALESCE(c.progressive_carries, 0)) AS ball_progressions,
                (COALESCE(ps.progressive_passes_under_pressure, 0)
                    + COALESCE(c.progressive_carries_under_pressure, 0))
                    AS ball_progressions_under_pressure
            FROM players p
            LEFT JOIN appearances a USING (player_id)
            LEFT JOIN shots s USING (player_id)
            LEFT JOIN passes ps USING (player_id)
            LEFT JOIN carries c USING (player_id)
            """
        )

        return {
            "mart_shots": con.execute(
                "SELECT count(*) FROM mart_shots"
            ).fetchone()[0],
            "mart_player_season": con.execute(
                "SELECT count(*) FROM mart_player_season"
            ).fetchone()[0],
        }
    finally:
        if own:
            con.close()
