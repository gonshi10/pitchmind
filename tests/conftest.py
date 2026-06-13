"""Shared fixtures for PitchMind tests."""

from __future__ import annotations

import pandas as pd
import pytest

from pitchmind import config
from pitchmind.etl import catalog, flatten


@pytest.fixture()
def tmp_data(tmp_path, monkeypatch):
    """Isolated data directory with catalog and two loaded targets."""
    data = tmp_path / "data"
    raw = data / "raw"
    parquet = data / "parquet"
    raw.mkdir(parents=True)
    parquet.mkdir(parents=True)

    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(config, "PARQUET_DIR", parquet)
    monkeypatch.setattr(config, "DB_PATH", data / "pitchmind.duckdb")
    monkeypatch.setattr(config, "STATE_PATH", data / "etl_state.json")
    monkeypatch.setattr(config, "CATALOG_PATH", raw / "catalog.parquet")
    monkeypatch.setattr(config, "MATCHES_PATH", raw / "matches.parquet")

    catalog_df = pd.DataFrame(
        [
            {
                "competition_id": 11,
                "season_id": 27,
                "competition_name": "La Liga",
                "season_name": "2015/2016",
                "country_name": "Spain",
                "competition_gender": "male",
                "competition_international": False,
            },
            {
                "competition_id": 43,
                "season_id": 3,
                "competition_name": "FIFA World Cup",
                "season_name": "2018",
                "country_name": "International",
                "competition_gender": "male",
                "competition_international": True,
            },
        ]
    )
    catalog_df.to_parquet(config.CATALOG_PATH, index=False)

    def _write_events(
        competition_id: int,
        season_id: int,
        match_id: int,
        player_id: int,
        player_name: str,
        team_id: int,
        team_name: str,
        goals: int,
    ) -> None:
        rows = []
        for i in range(goals):
            rows.append(
                {
                    "id": f"{match_id}-shot-{i}",
                    "match_id": match_id,
                    "competition_id": competition_id,
                    "season_id": season_id,
                    "type": "Shot",
                    "player_id": player_id,
                    "player": player_name,
                    "team_id": team_id,
                    "team": team_name,
                    "location_x": 110.0,
                    "location_y": 40.0,
                    "shot_outcome": "Goal",
                    "shot_statsbomb_xg": 0.5,
                    "under_pressure": False,
                }
            )
        rows.append(
            {
                "id": f"{match_id}-pass",
                "match_id": match_id,
                "competition_id": competition_id,
                "season_id": season_id,
                "type": "Pass",
                "player_id": player_id,
                "player": player_name,
                "team_id": team_id,
                "team": team_name,
                "location_x": 50.0,
                "location_y": 40.0,
                "pass_end_x": 70.0,
                "pass_end_y": 40.0,
                "pass_outcome": None,
                "under_pressure": False,
            }
        )
        df = pd.DataFrame(rows)
        for col in flatten.CURATED_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        df = df[flatten.CURATED_COLUMNS]
        path = flatten.match_parquet_path(match_id, competition_id, season_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)

    _write_events(11, 27, 1001, 5503, "Lionel Messi", 217, "Barcelona", 2)
    _write_events(43, 3, 2001, 5476, "Harry Kane", 781, "England", 6)

    return data
