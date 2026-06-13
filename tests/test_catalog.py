"""Tests for catalog sync and target resolution."""

from pitchmind import config
from pitchmind.etl import catalog


def test_all_targets_from_cache(tmp_data):
    targets = catalog.all_targets()
    assert len(targets) == 2
    labels = {t.label for t in targets}
    assert "La Liga 2015/2016" in labels
    assert "FIFA World Cup 2018" in labels


def test_get_target_by_ids(tmp_data):
    t = catalog.get_target(11, 27)
    assert t.competition_name == "La Liga"
    assert t.season_name == "2015/2016"


def test_resolve_target_name(tmp_data):
    t = catalog.resolve_target("World Cup 2018")
    assert t.competition_id == 43
    assert t.season_id == 3


def test_loaded_targets_from_parquet(tmp_data):
    loaded = catalog.loaded_targets_from_parquet()
    assert len(loaded) == 2
    keys = {(t.competition_id, t.season_id) for t in loaded}
    assert keys == {(11, 27), (43, 3)}


def test_target_season_key():
    t = config.LA_LIGA_2015_16
    assert t.season_key == "11:27"
