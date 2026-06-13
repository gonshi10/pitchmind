"""Assemble the cached prompt prefix from the three corpora."""

from __future__ import annotations

import json
from functools import lru_cache

from .. import config, llm
from ..etl import catalog
from .types import Scope


@lru_cache(maxsize=1)
def _schema_docs() -> str:
    return (config.KNOWLEDGE_DIR / "schema_docs.md").read_text()


@lru_cache(maxsize=1)
def _glossary() -> str:
    return (config.KNOWLEDGE_DIR / "glossary.md").read_text()


def _exemplars_for_scope(scope: Scope | None) -> str:
    path = config.KNOWLEDGE_DIR / "exemplars.jsonl"
    all_parts: list[str] = ["# Few-shot exemplars (question -> plan -> SQL)\n"]
    scoped_parts: list[str] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        ex = json.loads(line)
        block = [
            f"## {ex['question']}",
            "plan: " + json.dumps(ex["plan"]),
            "```sql\n" + ex["sql"] + "\n```\n",
        ]
        all_parts.extend(block)
        ex_scope = ex.get("scope")
        if scope and ex_scope:
            if (
                ex_scope.get("competition_id") == scope.competition_id
                and ex_scope.get("season_id") == scope.season_id
            ):
                scoped_parts.extend(block)
    parts = scoped_parts if scoped_parts else all_parts
    return "\n".join(parts)


def _loaded_targets_text() -> str:
    loaded = catalog.loaded_targets()
    if not loaded:
        return "No data loaded yet."
    lines = [t.label for t in loaded]
    return "\n".join(f"- {line}" for line in lines)


def _sql_instructions(scope: Scope | None) -> str:
    filter_line = (
        f"- Always filter `competition_id = {scope.competition_id} "
        f"AND season_id = {scope.season_id}`."
        if scope
        else "- Always filter competition_id AND season_id for the resolved scope."
    )
    return f"""You generate DuckDB SQL for PitchMind, a football analytics agent
over StatsBomb event data. You are given the database schema, a metric glossary, few-shot
exemplars, and a resolved query plan. Return only SQL.

Hard rules — a query that breaks any of these is rejected:
- A single read-only SELECT (CTEs allowed). No INSERT/UPDATE/DELETE/CREATE/ATTACH/COPY/PRAGMA.
- Reference only tables/views and columns that exist in the schema.
{filter_line}
- Always include a LIMIT.
- Prefer the marts (mart_player_season, mart_shots) over raw event views when they cover the metric.
- Filter resolved entities by the id given in the plan (player_id / team_id), not by name string.
- Use the glossary's exact definitions for fuzzy metrics."""


def _planner_system() -> str:
    return f"""You are the planner for PitchMind, a football analytics agent over
StatsBomb open event data.

Loaded competition/season data (only these can be queried):
{_loaded_targets_text()}

Classify the question and extract entities. Output strict JSON matching the schema.
- question_type: one of leaderboard, player_lookup, team_comparison, shot_map, aggregate.
- metric: a short phrase naming what is being measured.
- entities: every player or team name mentioned, each as {{text, kind}} where kind is
  "player" or "team". Empty list if none. Do NOT guess ids — resolution happens later.
- time_scope: the competition and season mentioned or implied (e.g. "La Liga 2015/16",
  "World Cup 2018"). Use the exact loaded label when possible.
- wants_viz: true only if a visual is clearly wanted (e.g. "show me ... shot map").
- viz_type: "shot_map" when a shot map fits, else null."""


def sql_gen_system(scope: Scope | None = None) -> list[dict]:
    """Cached system blocks for SQL generation."""
    return llm.cached_system(
        [
            _sql_instructions(scope),
            _schema_docs(),
            _glossary(),
            _exemplars_for_scope(scope),
        ],
        cache_last=True,
    )


def planner_system() -> str:
    return _planner_system()
