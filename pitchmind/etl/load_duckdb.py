"""Load flattened parquet into DuckDB and create typed per-event-type views."""

from __future__ import annotations

import duckdb

from .. import config

_BASE_COLS = [
    "id", "match_id", "competition_id", "season_id",
    "period", "minute", "second",
    "team", "team_id", "player", "player_id", "position",
    "location_x", "location_y", "under_pressure", "play_pattern",
]

VIEWS: dict[str, tuple[str, list[str]]] = {
    "v_shots": (
        "Shot",
        _BASE_COLS + [
            "shot_statsbomb_xg", "shot_outcome", "shot_type", "shot_body_part",
            "shot_technique", "shot_end_x", "shot_end_y", "shot_end_z",
            "shot_first_time", "shot_key_pass_id",
        ],
    ),
    "v_passes": (
        "Pass",
        _BASE_COLS + [
            "pass_recipient", "pass_recipient_id", "pass_length", "pass_angle",
            "pass_height", "pass_end_x", "pass_end_y", "pass_outcome", "pass_type",
            "pass_body_part", "pass_switch", "pass_cross", "pass_cut_back",
            "pass_shot_assist", "pass_goal_assist",
        ],
    ),
    "v_carries": ("Carry", _BASE_COLS + ["carry_end_x", "carry_end_y"]),
    "v_pressures": ("Pressure", _BASE_COLS + ["counterpress"]),
    "v_dribbles": ("Dribble", _BASE_COLS + ["dribble_outcome"]),
    "v_duels": ("Duel", _BASE_COLS + ["duel_type", "duel_outcome"]),
    "v_interceptions": ("Interception", _BASE_COLS + ["interception_outcome"]),
    "v_ball_receipts": ("Ball Receipt*", _BASE_COLS + ["ball_receipt_outcome"]),
}


def _parquet_sources() -> list[str]:
    """Globs for hive-partitioned and legacy flat parquet layouts."""
    sources: list[str] = []
    partitioned = config.PARQUET_DIR / "competition_id=*" / "season_id=*" / "events_match_*.parquet"
    if list(config.PARQUET_DIR.glob("competition_id=*")):
        sources.append(str(partitioned))
    legacy = config.PARQUET_DIR / "events_match_*.parquet"
    if list(config.PARQUET_DIR.glob("events_match_*.parquet")):
        sources.append(str(legacy))
    return sources


def load(con: duckdb.DuckDBPyConnection | None = None) -> dict[str, int]:
    """(Re)build the ``events`` table from parquet and create the typed views."""
    own = con is None
    if con is None:
        config.ensure_dirs()
        con = duckdb.connect(str(config.DB_PATH), read_only=False)

    try:
        sources = _parquet_sources()
        if not sources:
            raise FileNotFoundError(
                f"No parquet files under {config.PARQUET_DIR}. "
                "Run `pitchmind etl add` first."
            )

        paths_sql = ", ".join(f"'{s}'" for s in sources)
        con.execute("DROP TABLE IF EXISTS events")
        con.execute(
            f"""
            CREATE TABLE events AS
            SELECT * FROM read_parquet([{paths_sql}], hive_partitioning=true)
            """
        )

        counts: dict[str, int] = {}
        counts["events"] = con.execute("SELECT count(*) FROM events").fetchone()[0]

        for view, (event_type, cols) in VIEWS.items():
            col_list = ", ".join(cols)
            con.execute(f"DROP VIEW IF EXISTS {view}")
            con.execute(
                f"CREATE VIEW {view} AS SELECT {col_list} FROM events "
                f"WHERE type = '{event_type}'"
            )
            counts[view] = con.execute(f"SELECT count(*) FROM {view}").fetchone()[0]

        from .. import db

        db.clear_schema_cache()
        return counts
    finally:
        if own:
            con.close()
