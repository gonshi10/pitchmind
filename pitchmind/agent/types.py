"""Shared dataclasses for the agent loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    time_scope: str = "La Liga 2015/2016"
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
    trace: dict[str, Any] = field(default_factory=dict)
