"""Regression: mart_player_season must not merge across competition/season."""

from pitchmind.etl import entity_index, load_duckdb, marts


def test_mart_player_season_grain(tmp_data):
    load_duckdb.load()
    entity_index.build()
    marts.build()

    import duckdb
    from pitchmind import config

    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    rows = con.execute(
        """
        SELECT competition_id, season_id, player_id, goals
        FROM mart_player_season
        ORDER BY competition_id, season_id, player_id
        """
    ).fetchall()
    con.close()

    assert len(rows) == 2
    goals_by_scope = {(int(r[0]), int(r[1])): int(r[3]) for r in rows}
    assert goals_by_scope[(11, 27)] == 2
    assert goals_by_scope[(43, 3)] == 6


def test_flatten_skips_existing_without_force(tmp_data):
    from pitchmind.etl import flatten

    import pandas as pd

    path = flatten.match_parquet_path(1001, 11, 27)
    assert path.exists()
    mtime_before = path.stat().st_mtime
    df = pd.read_parquet(path)
    flatten.write_match_parquet(df, 1001, 11, 27, force=False)
    assert path.stat().st_mtime == mtime_before
