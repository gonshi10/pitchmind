"""DuckDB access: a read-only connection for the agent and schema introspection.

The agent never gets a writable handle — only ETL does (``connect(read_only=False)``).
Schema introspection drives both the verifier (does this table/column exist?) and the
generated schema docs.
"""

from __future__ import annotations

from functools import lru_cache

import duckdb

from . import config


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Open a connection to the project DuckDB file.

    Args:
        read_only: When True (the default and the only mode the agent uses), the
            connection cannot mutate the database. ETL passes False.
    """
    if read_only and not config.DB_PATH.exists():
        raise FileNotFoundError(
            f"DuckDB file not found at {config.DB_PATH}. Run the ETL first: "
            "`pitchmind etl add --name 'La Liga 2015/16'` (or `pitchmind etl catalog` "
            "then `pitchmind etl add` for another target)."
        )
    config.ensure_dirs()
    return duckdb.connect(str(config.DB_PATH), read_only=read_only)


def _schema_map(con: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    """Return {table_or_view_name: [column, ...]} for the main schema."""
    rows = con.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'main'
        ORDER BY table_name, ordinal_position
        """
    ).fetchall()
    schema: dict[str, list[str]] = {}
    for table_name, column_name in rows:
        schema.setdefault(table_name, []).append(column_name)
    return schema


@lru_cache(maxsize=1)
def schema_map() -> dict[str, list[str]]:
    """Cached {table: [columns]} from a short-lived read-only connection."""
    con = connect(read_only=True)
    try:
        return _schema_map(con)
    finally:
        con.close()


def clear_schema_cache() -> None:
    """Invalidate cached schema after ETL rebuilds."""
    schema_map.cache_clear()


def relations() -> set[str]:
    """All table/view names in the main schema."""
    return set(schema_map().keys())


def columns(relation: str) -> set[str]:
    """Columns of a relation, or empty set if the relation does not exist."""
    return set(schema_map().get(relation, []))
