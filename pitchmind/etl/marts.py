"""Materialized metric marts."""

from __future__ import annotations

import duckdb

PROGRESSIVE_THRESHOLD = 10


def build(con: duckdb.DuckDBPyConnection | None = None) -> dict[str, int]:
    """Create ``mart_shots`` and ``mart_player_season``."""
    from .. import config

    own = con is None
    if con is None:
        con = duckdb.connect(str(config.DB_PATH), read_only=False)

    try:
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

        thr = PROGRESSIVE_THRESHOLD
        con.execute("DROP TABLE IF EXISTS mart_player_season")
        con.execute(
            f"""
            CREATE TABLE mart_player_season AS
            WITH shots AS (
                SELECT player_id, competition_id, season_id,
                       count(*) AS shots,
                       sum(CASE WHEN shot_outcome = 'Goal' THEN 1 ELSE 0 END) AS goals,
                       sum(shot_statsbomb_xg) AS xg
                FROM v_shots
                GROUP BY player_id, competition_id, season_id
            ),
            passes AS (
                SELECT player_id, competition_id, season_id,
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
                FROM v_passes
                GROUP BY player_id, competition_id, season_id
            ),
            carries AS (
                SELECT player_id, competition_id, season_id,
                       sum(CASE WHEN (carry_end_x - location_x) >= {thr}
                                THEN 1 ELSE 0 END) AS progressive_carries,
                       sum(CASE WHEN (carry_end_x - location_x) >= {thr}
                                 AND under_pressure
                                THEN 1 ELSE 0 END)
                           AS progressive_carries_under_pressure
                FROM v_carries
                GROUP BY player_id, competition_id, season_id
            ),
            appearances AS (
                SELECT player_id, competition_id, season_id,
                       count(DISTINCT match_id) AS matches_played
                FROM events
                WHERE player_id IS NOT NULL
                GROUP BY player_id, competition_id, season_id
            ),
            player_teams AS (
                SELECT player_id, competition_id, season_id,
                       player AS player_name, team AS team_name, team_id,
                       row_number() OVER (
                           PARTITION BY player_id, competition_id, season_id
                           ORDER BY count(*) DESC
                       ) AS rk
                FROM events
                WHERE player_id IS NOT NULL
                GROUP BY player_id, competition_id, season_id, player, team, team_id
            )
            SELECT
                pt.player_id, pt.player_name, pt.team_name, pt.team_id,
                pt.competition_id, pt.season_id,
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
            FROM player_teams pt
            JOIN appearances a
              ON pt.player_id = a.player_id
             AND pt.competition_id = a.competition_id
             AND pt.season_id = a.season_id
            LEFT JOIN shots s
              ON pt.player_id = s.player_id
             AND pt.competition_id = s.competition_id
             AND pt.season_id = s.season_id
            LEFT JOIN passes ps
              ON pt.player_id = ps.player_id
             AND pt.competition_id = ps.competition_id
             AND pt.season_id = ps.season_id
            LEFT JOIN carries c
              ON pt.player_id = c.player_id
             AND pt.competition_id = c.competition_id
             AND pt.season_id = c.season_id
            WHERE pt.rk = 1
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
