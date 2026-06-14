"""Flatten StatsBomb events into a stable, curated parquet table.

StatsBomb's raw event frame is ~100 sparse columns with nested ``location`` lists and
per-event-type sub-objects. We project it onto a curated, well-named column set so the
schema docs and generated SQL stay tractable. Locations are split into ``*_x`` / ``*_y``.

One parquet file per match under hive partitions:
``data/parquet/competition_id=X/season_id=Y/events_match_Z.parquet``.
"""

from __future__ import annotations

import warnings

import pandas as pd

from pathlib import Path

from .. import config
from . import catalog

warnings.filterwarnings("ignore", module="statsbombpy")

CURATED_COLUMNS: list[str] = [
    "id", "match_id", "competition_id", "season_id",
    "index", "period", "minute", "second", "timestamp",
    "type", "play_pattern", "possession", "possession_team",
    "team", "team_id", "player", "player_id", "position",
    "location_x", "location_y", "under_pressure", "duration",
    "counterpress",
    "pass_recipient", "pass_recipient_id", "pass_length", "pass_angle",
    "pass_height", "pass_end_x", "pass_end_y", "pass_outcome", "pass_type",
    "pass_body_part", "pass_switch", "pass_cross", "pass_cut_back",
    "pass_shot_assist", "pass_goal_assist",
    "carry_end_x", "carry_end_y",
    "shot_statsbomb_xg", "shot_outcome", "shot_type", "shot_body_part",
    "shot_technique", "shot_end_x", "shot_end_y", "shot_end_z", "shot_first_time",
    "shot_key_pass_id",
    "dribble_outcome", "duel_type", "duel_outcome", "interception_outcome",
    "ball_receipt_outcome",
]

BOOL_COLUMNS = [
    "under_pressure", "counterpress", "pass_switch", "pass_cross", "pass_cut_back",
    "pass_shot_assist", "pass_goal_assist", "shot_first_time",
]


def _split_location(df: pd.DataFrame, src: str, x: str, y: str, z: str | None = None) -> None:
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


def flatten_events(
    events: pd.DataFrame,
    match_id: int,
    competition_id: int,
    season_id: int,
) -> pd.DataFrame:
    """Project a raw statsbombpy events frame onto the curated schema."""
    df = events.copy()
    df["match_id"] = match_id
    df["competition_id"] = competition_id
    df["season_id"] = season_id

    _split_location(df, "location", "location_x", "location_y")
    _split_location(df, "pass_end_location", "pass_end_x", "pass_end_y")
    _split_location(df, "carry_end_location", "carry_end_x", "carry_end_y")
    _split_location(df, "shot_end_location", "shot_end_x", "shot_end_y", "shot_end_z")

    for col in CURATED_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    out = df[CURATED_COLUMNS].copy()

    for col in BOOL_COLUMNS:
        out[col] = out[col].fillna(False).astype(bool)

    return out


def match_parquet_path(
    match_id: int,
    competition_id: int,
    season_id: int,
) -> Path:
    partition = catalog.partition_dir(competition_id, season_id)
    return partition / f"events_match_{match_id}.parquet"


def fetch_and_flatten_match(
    match_id: int,
    competition_id: int,
    season_id: int,
) -> pd.DataFrame:
    """Fetch one match's events and return the curated flat frame."""
    from statsbombpy import sb

    events = sb.events(match_id=match_id)
    return flatten_events(events, match_id, competition_id, season_id)


def write_match_parquet(
    df: pd.DataFrame,
    match_id: int,
    competition_id: int,
    season_id: int,
    force: bool = False,
) -> str:
    """Write one match's flat events to parquet; return the path."""
    config.ensure_dirs()
    path = match_parquet_path(match_id, competition_id, season_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return str(path)
    df.to_parquet(path, index=False)
    return str(path)


def flatten_target(target: config.Target, force: bool = False) -> tuple[int, int]:
    """Flatten all cached matches for one target. Returns (matches_written, event_count)."""
    from . import download

    matches = download.cached_matches(target.competition_id, target.season_id)
    total_matches = len(matches)
    event_count = 0
    for i, row in enumerate(matches.itertuples(index=False), start=1):
        match_id = int(row.match_id)
        df = fetch_and_flatten_match(
            match_id, target.competition_id, target.season_id
        )
        write_match_parquet(
            df, match_id, target.competition_id, target.season_id, force=force
        )
        event_count += len(df)
    return total_matches, event_count
