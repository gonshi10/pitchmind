"""Download step: verify the target competition/season and cache the match list.

Event fetching happens in ``flatten`` (one network call per match). This step validates
connectivity and the configured ids up front, and persists the match list so later steps
know what to flatten.
"""

from __future__ import annotations

import warnings

import pandas as pd

from .. import config

warnings.filterwarnings("ignore", module="statsbombpy")

MATCHES_PATH = lambda: config.RAW_DIR / "matches.parquet"  # noqa: E731


def verify_target() -> None:
    """Assert the configured competition/season exists in StatsBomb open data."""
    from statsbombpy import sb

    comps = sb.competitions()
    match = comps[
        (comps["competition_id"] == config.TARGET.competition_id)
        & (comps["season_id"] == config.TARGET.season_id)
    ]
    if match.empty:
        raise ValueError(
            f"Target {config.TARGET.label} "
            f"(competition_id={config.TARGET.competition_id}, "
            f"season_id={config.TARGET.season_id}) not found in sb.competitions(). "
            "Check the ids in pitchmind/config.py against the open-data catalog."
        )


def download_matches() -> pd.DataFrame:
    """Fetch and cache the match list for the target. Returns the frame."""
    from statsbombpy import sb

    config.ensure_dirs()
    verify_target()
    matches = sb.matches(
        competition_id=config.TARGET.competition_id,
        season_id=config.TARGET.season_id,
    )
    # The raw matches frame carries messy columns (e.g. comma-joined manager ids) that
    # don't serialize to parquet. We only need the match list + a little context.
    keep = [
        c
        for c in ["match_id", "match_date", "home_team", "away_team",
                  "home_score", "away_score"]
        if c in matches.columns
    ]
    clean = matches[keep].copy()
    clean["match_id"] = clean["match_id"].astype("int64")
    clean.to_parquet(MATCHES_PATH(), index=False)
    return clean


def cached_match_ids() -> list[int]:
    """Match ids from the cached match list (run ``download`` first)."""
    path = MATCHES_PATH()
    if not path.exists():
        raise FileNotFoundError(
            f"No cached match list at {path}. Run `pitchmind etl download` first."
        )
    matches = pd.read_parquet(path)
    return [int(m) for m in matches["match_id"].tolist()]
