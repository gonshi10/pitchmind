"""Persist agent run traces as JSON files under data/traces/.

The trace is the showcase + debugging artifact (CLAUDE.md). Phase 2 persists each run so the
web app's "how I got this" panel and ``GET /trace/{id}`` can fetch it. No database — a file
per run, keyed by run_id.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config

TRACES_DIR = config.DATA_DIR / "traces"


def _path(run_id: str) -> Path:
    # run_id is a uuid4 we mint ourselves; basename-guard anyway.
    safe = Path(run_id).name
    return TRACES_DIR / f"{safe}.json"


def save(run_id: str, trace: dict) -> None:
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    _path(run_id).write_text(json.dumps(trace, indent=2, default=str))


def load(run_id: str) -> dict | None:
    path = _path(run_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())
