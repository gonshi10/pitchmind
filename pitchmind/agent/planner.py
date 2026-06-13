"""Planner: classify the question and extract entities as strict JSON."""

from __future__ import annotations

from .. import llm
from . import retrieval
from .types import Entity, Plan

_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "question_type": {
            "type": "string",
            "enum": [
                "leaderboard",
                "player_lookup",
                "team_comparison",
                "shot_map",
                "aggregate",
            ],
        },
        "metric": {"type": "string"},
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "kind": {"type": "string", "enum": ["player", "team"]},
                },
                "required": ["text", "kind"],
            },
        },
        "time_scope": {"type": "string"},
        "wants_viz": {"type": "boolean"},
        "viz_type": {"type": "string", "enum": ["shot_map", "none"]},
    },
    "required": [
        "question_type",
        "metric",
        "entities",
        "time_scope",
        "wants_viz",
        "viz_type",
    ],
}


def plan(question: str) -> Plan:
    data = llm.complete(
        retrieval.planner_system(),
        f"Question: {question}",
        max_tokens=600,
        json_schema=_PLAN_SCHEMA,
    )
    assert isinstance(data, dict)
    viz_type = data.get("viz_type")
    if viz_type == "none":
        viz_type = None
    return Plan(
        question_type=data["question_type"],
        metric=data["metric"],
        entities=[Entity(text=e["text"], kind=e["kind"]) for e in data["entities"]],
        time_scope=data.get("time_scope", ""),
        wants_viz=bool(data.get("wants_viz", False)),
        viz_type=viz_type,
    )
