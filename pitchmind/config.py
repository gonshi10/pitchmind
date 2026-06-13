"""Central configuration: paths, model, and competition/season targets.

StatsBomb open-data ids are verified at runtime against ``sb.competitions()`` during ETL
rather than trusted blindly. Multiple competition/season pairs can be loaded; see
``pitchmind etl catalog`` and ``pitchmind etl add``.
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
STATE_PATH = DATA_DIR / "etl_state.json"
CATALOG_PATH = RAW_DIR / "catalog.parquet"
MATCHES_PATH = RAW_DIR / "matches.parquet"

# --- LLM ------------------------------------------------------------------------
MODEL = os.environ.get("PITCHMIND_MODEL", "claude-opus-4-8")

# --- Execution safety caps (spec §3) --------------------------------------------
ROW_CAP = 200          # hard cap on rows returned by any query
STATEMENT_TIMEOUT_S = 15  # per-statement wall-clock budget for the executor
MAX_REPAIRS = 1        # at most one SQL repair loop
SYNTHESIS_TOP_N = 30   # rows shown to the synthesis model (token discipline)


@dataclass(frozen=True)
class Target:
    """A competition/season pair from the StatsBomb open-data catalog."""

    competition_id: int
    season_id: int
    competition_name: str
    season_name: str

    @property
    def label(self) -> str:
        return f"{self.competition_name} {self.season_name}"

    @property
    def season_key(self) -> str:
        """Composite key for season-scoped aliases (competition_id:season_id)."""
        return f"{self.competition_id}:{self.season_id}"


# Default target for examples and backward-compatible CLI defaults.
LA_LIGA_2015_16 = Target(
    competition_id=11,
    season_id=27,
    competition_name="La Liga",
    season_name="2015/2016",
)

DEFAULT_TARGET = LA_LIGA_2015_16

# Backward compatibility alias.
TARGET = DEFAULT_TARGET


def ensure_dirs() -> None:
    """Create the gitignored data directories if missing."""
    for d in (DATA_DIR, RAW_DIR, PARQUET_DIR):
        d.mkdir(parents=True, exist_ok=True)
