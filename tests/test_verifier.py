"""Tests for SQL verifier scope and WHERE enforcement."""

from pitchmind.agent import verifier
from pitchmind.agent.types import Scope
from pitchmind.etl import entity_index, load_duckdb, marts


SCOPE = Scope(competition_id=11, season_id=27, label="La Liga 2015/2016")


def test_accepts_valid_scoped_sql(tmp_data):
    load_duckdb.load()
    entity_index.build()
    marts.build()
    sql = (
        "SELECT player_name, goals FROM mart_player_season "
        "WHERE competition_id = 11 AND season_id = 27 ORDER BY goals DESC LIMIT 10"
    )
    result = verifier.verify(sql, scope=SCOPE)
    assert result.ok


def test_rejects_missing_where_filters():
    sql = "SELECT competition_id, season_id, goals FROM mart_player_season LIMIT 10"
    result = verifier.verify(sql, scope=SCOPE)
    assert not result.ok
    assert any("WHERE" in e for e in result.errors)


def test_rejects_wrong_scope_ids():
    sql = (
        "SELECT goals FROM mart_player_season "
        "WHERE competition_id = 43 AND season_id = 3 LIMIT 10"
    )
    result = verifier.verify(sql, scope=SCOPE)
    assert not result.ok
    assert any("competition_id = 11" in e for e in result.errors)


def test_rejects_forbidden_keyword():
    sql = (
        "DELETE FROM mart_player_season "
        "WHERE competition_id = 11 AND season_id = 27"
    )
    result = verifier.verify(sql, scope=SCOPE)
    assert not result.ok
