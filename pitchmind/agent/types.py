"""Shared dataclasses for the agent loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Scope:
    """Resolved competition/season for a question."""

    competition_id: int
    season_id: int
    label: str
    confidence: float | None = None
    note: str | None = None


@dataclass
class Entity:
    """An entity extracted by the planner and (optionally) resolved to an id."""

    text: str
    kind: str  # "player" | "team"
    entity_id: int | None = None
    resolved_name: str | None = None
    confidence: float | None = None
    note: str | None = None


@dataclass
class Plan:
    """Structured output of the planner."""

    question_type: str
    metric: str
    entities: list[Entity] = field(default_factory=list)
    time_scope: str = ""
    scope: Scope | None = None
    wants_viz: bool = False
    viz_type: str | None = None


@dataclass
class AgentResult:
    """What the loop returns to the CLI/API."""

    answer: str
    sql: str | None = None
    rows: list[dict] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    viz_path: str | None = None
    ok: bool = True
    run_id: str = ""
    trace: dict[str, Any] = field(default_factory=dict)
