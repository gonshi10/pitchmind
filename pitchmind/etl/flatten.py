"""Flatten StatsBomb events into a stable, curated parquet table.

StatsBomb's raw event frame is ~100 sparse columns with nested ``location`` lists and
per-event-type sub-objects. We project it onto a curated, well-named column set so the
schema docs and generated SQL stay tractable. Locations are split into ``*_x`` / ``*_y``.

One parquet file is written per match under ``data/parquet/`` so the step is incremental.
"""

from __future__ import annotations

import warnings

import pandas as pd

from .. import config

# statsbombpy is chatty and warns about the no-auth open-data path; quiet it.
warnings.filterwarnings("ignore", module="statsbombpy")


# Curated output columns, in order. Missing source columns are filled with NA so every
# match parquet has an identical schema.
CURATED_COLUMNS: list[str] = [
    # identity / context
    "id", "match_id", "competition_id", "season_id",
    "index", "period", "minute", "second", "timestamp",
    "type", "play_pattern", "possession", "possession_team",
    "team", "team_id", "player", "player_id", "position",
    "location_x", "location_y", "under_pressure", "duration",
    "counterpress",
    # pass
    "pass_recipient", "pass_recipient_id", "pass_length", "pass_angle",
    "pass_height", "pass_end_x", "pass_end_y", "pass_outcome", "pass_type",
    "pass_body_part", "pass_switch", "pass_cross", "pass_cut_back",
    "pass_shot_assist", "pass_goal_assist",
    # carry
    "carry_end_x", "carry_end_y",
    # shot
    "shot_statsbomb_xg", "shot_outcome", "shot_type", "shot_body_part",
    "shot_technique", "shot_end_x", "shot_end_y", "shot_end_z", "shot_first_time",
    "shot_key_pass_id",
    # dribble / duel / interception / receipt
    "dribble_outcome", "duel_type", "duel_outcome", "interception_outcome",
    "ball_receipt_outcome",
]

BOOL_COLUMNS = [
    "under_pressure", "counterpress", "pass_switch", "pass_cross", "pass_cut_back",
    "pass_shot_assist", "pass_goal_assist", "shot_first_time",
]


def _split_location(df: pd.DataFrame, src: str, x: str, y: str, z: str | None = None) -> None:
    """Split a [x, y(, z)] list column into numeric columns; tolerate absence/NaN."""
    if src not in df.columns:
        df[x] = pd.NA
        df[y] = pd.NA
        if z:
            df[z] = pd.NA
        return

    def _get(v, i):
        if isinstance(v, (list, tuple)) and len(v) > i:
            return v[i]
        return pd.NA

    df[x] = df[src].map(lambda v: _get(v, 0))
    df[y] = df[src].map(lambda v: _get(v, 1))
    if z:
        df[z] = df[src].map(lambda v: _get(v, 2))


def flatten_events(events: pd.DataFrame, match_id: int) -> pd.DataFrame:
    """Project a raw statsbombpy events frame onto the curated schema."""
    df = events.copy()
    df["match_id"] = match_id
    df["competition_id"] = config.TARGET.competition_id
    df["season_id"] = config.TARGET.season_id

    _split_location(df, "location", "location_x", "location_y")
    _split_location(df, "pass_end_location", "pass_end_x", "pass_end_y")
    _split_location(df, "carry_end_location", "carry_end_x", "carry_end_y")
    _split_location(df, "shot_end_location", "shot_end_x", "shot_end_y", "shot_end_z")

    # Ensure every curated column exists (fill absent ones with NA).
    for col in CURATED_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    out = df[CURATED_COLUMNS].copy()

    # Normalize booleans: StatsBomb encodes flags as True / missing.
    for col in BOOL_COLUMNS:
        out[col] = out[col].fillna(False).astype(bool)

    return out


def match_list() -> pd.DataFrame:
    """All matches for the configured target competition/season."""
    from statsbombpy import sb  # imported lazily so non-ETL paths don't need it

    return sb.matches(
        competition_id=config.TARGET.competition_id,
        season_id=config.TARGET.season_id,
    )


def fetch_and_flatten_match(match_id: int) -> pd.DataFrame:
    """Fetch one match's events and return the curated flat frame."""
    from statsbombpy import sb

    events = sb.events(match_id=match_id)
    return flatten_events(events, match_id)


def write_match_parquet(df: pd.DataFrame, match_id: int) -> str:
    """Write one match's flat events to parquet; return the path."""
    config.ensure_dirs()
    path = config.PARQUET_DIR / f"events_match_{match_id}.parquet"
    df.to_parquet(path, index=False)
    return str(path)
