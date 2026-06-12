"""Central configuration: paths, model, and the target competition/season.

Phase 1 is scoped to La Liga 2015/16 only (spec §8). StatsBomb open-data ids:
competition_id=11 (La Liga), season_id=27 (2015/2016). These are verified at runtime
against ``sb.competitions()`` during ``etl download`` rather than trusted blindly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env, then .env.local (local overrides win). Real secrets never live in code.
load_dotenv()
load_dotenv(".env.local", override=True)

# --- Repo paths -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PARQUET_DIR = DATA_DIR / "parquet"
KNOWLEDGE_DIR = ROOT / "knowledge"
EVAL_DIR = ROOT / "eval"

DB_PATH = Path(os.environ.get("PITCHMIND_DB", str(DATA_DIR / "pitchmind.duckdb")))

# --- LLM ------------------------------------------------------------------------
MODEL = os.environ.get("PITCHMIND_MODEL", "claude-opus-4-8")

# --- Execution safety caps (spec §3) --------------------------------------------
ROW_CAP = 200          # hard cap on rows returned by any query
STATEMENT_TIMEOUT_S = 15  # per-statement wall-clock budget for the executor
MAX_REPAIRS = 1        # at most one SQL repair loop
SYNTHESIS_TOP_N = 30   # rows shown to the synthesis model (token discipline)


@dataclass(frozen=True)
class Target:
    """The competition/season this build is scoped to."""

    competition_id: int
    season_id: int
    competition_name: str
    season_name: str

    @property
    def label(self) -> str:
        return f"{self.competition_name} {self.season_name}"


# Phase 1 target. season_name uses StatsBomb's "2015/2016" formatting.
LA_LIGA_2015_16 = Target(
    competition_id=11,
    season_id=27,
    competition_name="La Liga",
    season_name="2015/2016",
)

# The single active target for Phase 1. Widening to more competitions is Phase 4.
TARGET = LA_LIGA_2015_16


def ensure_dirs() -> None:
    """Create the gitignored data directories if missing."""
    for d in (DATA_DIR, RAW_DIR, PARQUET_DIR):
        d.mkdir(parents=True, exist_ok=True)
