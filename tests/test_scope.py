"""Tests for scope resolution."""

from pitchmind.agent import scope
from pitchmind.agent.types import Plan
from pitchmind.etl import entity_index, load_duckdb


def test_single_loaded_target_auto_scope(tmp_data):
    """With one target loaded, scope resolves without naming the league."""
    from pitchmind.etl import flatten

    # Remove World Cup partition so only La Liga is loaded.
    wc_path = flatten.match_parquet_path(2001, 43, 3)
    wc_path.unlink()

    plan = Plan(question_type="leaderboard", metric="goals", time_scope="")
    result = scope.resolve_scope("Who scored the most goals?", plan)
    assert result.scope is not None
    assert result.scope.competition_id == 11
    assert result.scope.season_id == 27


def test_resolve_world_cup_from_question(tmp_data):
    load_duckdb.load()
    entity_index.build()

    plan = Plan(
        question_type="leaderboard",
        metric="goals",
        time_scope="FIFA World Cup 2018",
    )
    result = scope.resolve_scope(
        "Who scored the most goals in the 2018 World Cup?", plan
    )
    assert result.scope is not None
    assert result.scope.competition_id == 43
    assert result.scope.season_id == 3


def test_ambiguous_scope_with_multiple_targets(tmp_data):
    plan = Plan(question_type="leaderboard", metric="goals", time_scope="")
    result = scope.resolve_scope("Who scored the most goals?", plan)
    assert result.error is not None
    assert "competition" in result.error.lower()
