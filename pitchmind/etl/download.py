"""Download step: cache match lists per competition/season.

Event fetching happens in ``flatten`` (one network call per match). This module validates
targets against the catalog and persists match metadata for later flatten steps.
"""

from __future__ import annotations

import warnings

import pandas as pd

from .. import config
from . import catalog

warnings.filterwarnings("ignore", module="statsbombpy")

MATCH_KEEP = [
    "match_id",
    "match_date",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
]


def verify_target(target: config.Target) -> None:
    """Assert the target exists in the cached catalog."""
    catalog.get_target(target.competition_id, target.season_id)


def download_matches(target: config.Target) -> pd.DataFrame:
    """Fetch and upsert the match list for one target. Returns the target's matches."""
    from statsbombpy import sb

    config.ensure_dirs()
    verify_target(target)
    matches = sb.matches(
        competition_id=target.competition_id,
        season_id=target.season_id,
    )
    keep = [c for c in MATCH_KEEP if c in matches.columns]
    clean = matches[keep].copy()
    clean["match_id"] = clean["match_id"].astype("int64")
    clean["competition_id"] = target.competition_id
    clean["season_id"] = target.season_id
    clean["competition_name"] = target.competition_name
    clean["season_name"] = target.season_name

    path = config.MATCHES_PATH
    if path.exists():
        existing = pd.read_parquet(path)
        # Drop rows for this target, then append fresh list.
        mask = (
            (existing["competition_id"] != target.competition_id)
            | (existing["season_id"] != target.season_id)
        )
        merged = pd.concat([existing[mask], clean], ignore_index=True)
    else:
        merged = clean

    merged.to_parquet(path, index=False)
    return clean


def cached_matches(
    competition_id: int | None = None,
    season_id: int | None = None,
) -> pd.DataFrame:
    """Read cached matches, optionally filtered to one competition/season."""
    path = config.MATCHES_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"No cached match list at {path}. "
            "Run `pitchmind etl add` for a competition/season first."
        )
    matches = pd.read_parquet(path)
    if competition_id is not None and season_id is not None:
        matches = matches[
            (matches["competition_id"] == competition_id)
            & (matches["season_id"] == season_id)
        ]
    return matches


def cached_match_ids(
    competition_id: int | None = None,
    season_id: int | None = None,
) -> list[int]:
    """Match ids from the cache, optionally scoped to one target."""
    matches = cached_matches(competition_id, season_id)
    return [int(m) for m in matches["match_id"].tolist()]
