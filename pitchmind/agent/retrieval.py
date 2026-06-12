"""Assemble the cached prompt prefix from the three corpora.

Phase 1 "RAG" is inline-all: the corpora are tiny for one season, so every SQL-generation
call gets the full schema docs + glossary + all exemplars as a stable, cached system prefix.
Real top-K retrieval is deferred to Phase 3 when the exemplar set grows.
"""

from __future__ import annotations

import json
from functools import lru_cache

from .. import config, llm


@lru_cache(maxsize=1)
def _schema_docs() -> str:
    return (config.KNOWLEDGE_DIR / "schema_docs.md").read_text()


@lru_cache(maxsize=1)
def _glossary() -> str:
    return (config.KNOWLEDGE_DIR / "glossary.md").read_text()


@lru_cache(maxsize=1)
def _exemplars_block() -> str:
    """Format the exemplar triples as readable few-shots."""
    path = config.KNOWLEDGE_DIR / "exemplars.jsonl"
    parts = ["# Few-shot exemplars (question -> plan -> SQL)\n"]
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        ex = json.loads(line)
        parts.append(f"## {ex['question']}")
        parts.append("plan: " + json.dumps(ex["plan"]))
        parts.append("```sql\n" + ex["sql"] + "\n```\n")
    return "\n".join(parts)


_SQL_INSTRUCTIONS = """You generate DuckDB SQL for PitchMind, a football analytics agent
over StatsBomb event data. You are given the database schema, a metric glossary, few-shot
exemplars, and a resolved query plan. Return only SQL.

Hard rules — a query that breaks any of these is rejected:
- A single read-only SELECT (CTEs allowed). No INSERT/UPDATE/DELETE/CREATE/ATTACH/COPY/PRAGMA.
- Reference only tables/views and columns that exist in the schema.
- Always filter `competition_id = 11 AND season_id = 27`.
- Always include a LIMIT.
- Prefer the marts (mart_player_season, mart_shots) over raw event views when they cover the metric.
- Filter resolved entities by the id given in the plan (player_id / team_id), not by name string.
- Use the glossary's exact definitions for fuzzy metrics."""


def sql_gen_system() -> list[dict]:
    """Cached system blocks for SQL generation (the big stable prefix)."""
    return llm.cached_system(
        [_SQL_INSTRUCTIONS, _schema_docs(), _glossary(), _exemplars_block()],
        cache_last=True,
    )


_PLANNER_SYSTEM = """You are the planner for PitchMind, a football analytics agent over
StatsBomb data for La Liga 2015/2016 only.

Classify the question and extract entities. Output strict JSON matching the schema.
- question_type: one of leaderboard, player_lookup, team_comparison, shot_map, aggregate.
- metric: a short phrase naming what is being measured (e.g. "goals", "ball progression
  under pressure", "shots with xG").
- entities: every player or team name mentioned, each as {text, kind} where kind is
  "player" or "team". Empty list if none. Do NOT guess ids — resolution happens later.
- time_scope: always "La Liga 2015/2016".
- wants_viz: true only if a visual is clearly wanted (e.g. "show me ... shot map", "map of").
- viz_type: "shot_map" when a shot map fits, else null."""


def planner_system() -> str:
    return _PLANNER_SYSTEM
