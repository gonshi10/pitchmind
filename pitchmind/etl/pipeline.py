"""Offline ETL orchestration helpers."""

from __future__ import annotations

from .. import config
from . import catalog, download, entity_index, flatten, load_duckdb, marts


def ingest_target(target: config.Target, force: bool = False) -> dict:
    """Full ingest pipeline for one competition/season."""
    download.download_matches(target)
    match_count, event_count = flatten.flatten_target(target, force=force)
    load_counts = load_duckdb.load()
    from .. import db

    db.clear_schema_cache()
    entity_counts = entity_index.build()
    mart_counts = marts.build()
    catalog.update_target_state(target, match_count, event_count)
    return {
        "target": target.label,
        "matches": match_count,
        "events_flattened": event_count,
        "load": load_counts,
        "entity_index": entity_counts,
        "marts": mart_counts,
    }


def rebuild_derived() -> dict:
    """Rebuild DuckDB views, entity index, and marts from existing parquet (no network)."""
    load_counts = load_duckdb.load()
    from .. import db

    db.clear_schema_cache()
    entity_counts = entity_index.build()
    mart_counts = marts.build()
    return {
        "load": load_counts,
        "entity_index": entity_counts,
        "marts": mart_counts,
    }
