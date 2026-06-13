"""StatsBomb open-data catalog: sync, resolve, and track loaded targets."""

from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

from .. import config

warnings.filterwarnings("ignore", module="statsbombpy")


def _catalog_path() -> Path:
    return config.CATALOG_PATH


def _row_to_target(row: pd.Series) -> config.Target:
    return config.Target(
        competition_id=int(row["competition_id"]),
        season_id=int(row["season_id"]),
        competition_name=str(row["competition_name"]),
        season_name=str(row["season_name"]),
    )


def sync_catalog() -> int:
    """Fetch ``sb.competitions()`` and persist to ``data/raw/catalog.parquet``."""
    from statsbombpy import sb

    config.ensure_dirs()
    comps = sb.competitions()
    comps.to_parquet(_catalog_path(), index=False)
    return len(comps)


def read_catalog() -> pd.DataFrame:
    """Read the cached catalog; sync first if missing."""
    path = _catalog_path()
    if not path.exists():
        sync_catalog()
    return pd.read_parquet(path)


def all_targets() -> list[config.Target]:
    """Every competition/season in the cached catalog."""
    df = read_catalog()
    return [_row_to_target(row) for _, row in df.iterrows()]


def get_target(competition_id: int, season_id: int) -> config.Target:
    """Look up one target by ids; raises ValueError if not in catalog."""
    df = read_catalog()
    match = df[
        (df["competition_id"] == competition_id) & (df["season_id"] == season_id)
    ]
    if match.empty:
        raise ValueError(
            f"competition_id={competition_id}, season_id={season_id} not in catalog. "
            "Run `pitchmind etl catalog` to refresh."
        )
    return _row_to_target(match.iloc[0])


def resolve_target(name: str) -> config.Target:
    """Fuzzy-match a human label like 'World Cup 2018' to a catalog target."""
    df = read_catalog()
    labels = [
        f"{row['competition_name']} {row['season_name']}" for _, row in df.iterrows()
    ]
    result = process.extractOne(name, labels, scorer=fuzz.WRatio)
    if result is None or result[1] < 70:
        raise ValueError(
            f"Could not resolve target name '{name}'. "
            "Try `pitchmind etl list` for available labels."
        )
    idx = labels.index(result[0])
    return _row_to_target(df.iloc[idx])


def partition_dir(competition_id: int, season_id: int) -> Path:
    """Hive partition directory for one competition/season."""
    return (
        config.PARQUET_DIR
        / f"competition_id={competition_id}"
        / f"season_id={season_id}"
    )


def loaded_targets_from_parquet() -> list[config.Target]:
    """Distinct targets with at least one parquet file on disk."""
    if not config.PARQUET_DIR.exists():
        return []
    targets: list[config.Target] = []
    df = read_catalog()
    catalog_map = {
        (int(r["competition_id"]), int(r["season_id"])): _row_to_target(r)
        for _, r in df.iterrows()
    }
    for comp_dir in config.PARQUET_DIR.glob("competition_id=*"):
        try:
            comp_id = int(comp_dir.name.split("=", 1)[1])
        except ValueError:
            continue
        for season_dir in comp_dir.glob("season_id=*"):
            try:
                season_id = int(season_dir.name.split("=", 1)[1])
            except ValueError:
                continue
            if any(season_dir.glob("events_match_*.parquet")):
                key = (comp_id, season_id)
                if key in catalog_map:
                    targets.append(catalog_map[key])
                else:
                    targets.append(
                        config.Target(
                            competition_id=comp_id,
                            season_id=season_id,
                            competition_name=f"competition_{comp_id}",
                            season_name=f"season_{season_id}",
                        )
                    )
    return sorted(targets, key=lambda t: (t.competition_id, t.season_id))


def loaded_targets_from_db() -> list[config.Target]:
    """Distinct targets present in DuckDB ``events``, if the DB exists."""
    if not config.DB_PATH.exists():
        return []
    import duckdb

    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT DISTINCT competition_id, season_id
            FROM events
            ORDER BY competition_id, season_id
            """
        ).fetchall()
    except duckdb.CatalogException:
        return []
    finally:
        con.close()

    df = read_catalog()
    catalog_map = {
        (int(r["competition_id"]), int(r["season_id"])): _row_to_target(r)
        for _, r in df.iterrows()
    }
    out: list[config.Target] = []
    for comp_id, season_id in rows:
        key = (int(comp_id), int(season_id))
        if key in catalog_map:
            out.append(catalog_map[key])
        else:
            out.append(
                config.Target(
                    competition_id=key[0],
                    season_id=key[1],
                    competition_name=f"competition_{key[0]}",
                    season_name=f"season_{key[1]}",
                )
            )
    return out


def loaded_targets() -> list[config.Target]:
    """Loaded targets: prefer DuckDB if present, else parquet partitions."""
    db_targets = loaded_targets_from_db()
    if db_targets:
        return db_targets
    return loaded_targets_from_parquet()


def read_state() -> dict:
    """Per-target ETL state from ``data/etl_state.json``."""
    if not config.STATE_PATH.exists():
        return {"targets": {}}
    return json.loads(config.STATE_PATH.read_text())


def write_state(state: dict) -> None:
    config.ensure_dirs()
    config.STATE_PATH.write_text(json.dumps(state, indent=2))


def update_target_state(
    target: config.Target,
    match_count: int,
    event_count: int | None = None,
) -> None:
    """Record successful ingest for one target."""
    state = read_state()
    key = target.season_key
    state["targets"][key] = {
        "competition_id": target.competition_id,
        "season_id": target.season_id,
        "label": target.label,
        "match_count": match_count,
        "event_count": event_count,
        "last_run": datetime.now(timezone.utc).isoformat(),
    }
    write_state(state)


def target_stats(target: config.Target) -> dict:
    """Match and event counts for one loaded target."""
    partition = partition_dir(target.competition_id, target.season_id)
    match_files = list(partition.glob("events_match_*.parquet"))
    match_count = len(match_files)
    event_count: int | None = None
    if config.DB_PATH.exists():
        import duckdb

        con = duckdb.connect(str(config.DB_PATH), read_only=True)
        try:
            row = con.execute(
                """
                SELECT count(*) FROM events
                WHERE competition_id = ? AND season_id = ?
                """,
                [target.competition_id, target.season_id],
            ).fetchone()
            event_count = int(row[0]) if row else 0
        except duckdb.CatalogException:
            event_count = None
        finally:
            con.close()
    return {"match_count": match_count, "event_count": event_count}
