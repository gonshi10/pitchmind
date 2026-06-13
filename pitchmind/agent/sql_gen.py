"""Generate DuckDB SQL from a resolved plan, grounded in the cached schema/glossary/exemplars."""

from __future__ import annotations

import json

from .. import llm
from . import retrieval
from .types import Plan

_SQL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"sql": {"type": "string"}},
    "required": ["sql"],
}


def _plan_brief(plan: Plan) -> str:
    resolved = []
    for e in plan.entities:
        if e.entity_id is not None:
            resolved.append(
                f"- {e.kind} '{e.text}' -> {e.resolved_name} ({e.kind}_id={e.entity_id})"
            )
        else:
            resolved.append(f"- {e.kind} '{e.text}' -> UNRESOLVED ({e.note})")
    plan_obj: dict = {
        "question_type": plan.question_type,
        "metric": plan.metric,
        "time_scope": plan.time_scope,
        "wants_viz": plan.wants_viz,
        "viz_type": plan.viz_type,
    }
    if plan.scope:
        plan_obj["scope"] = {
            "competition_id": plan.scope.competition_id,
            "season_id": plan.scope.season_id,
            "label": plan.scope.label,
        }
    lines = ["plan: " + json.dumps(plan_obj)]
    if resolved:
        lines.append("Resolved entities (filter by these ids):")
        lines.extend(resolved)
    return "\n".join(lines)


def generate(question: str, plan: Plan, repair: str | None = None) -> str:
    user = f"Question: {question}\n{_plan_brief(plan)}"
    if repair:
        user += (
            "\n\nThe previous SQL was rejected. Fix it and return corrected SQL.\n"
            + repair
        )
    data = llm.complete(
        retrieval.sql_gen_system(plan.scope),
        user,
        max_tokens=1200,
        json_schema=_SQL_SCHEMA,
    )
    assert isinstance(data, dict)
    return data["sql"].strip()
