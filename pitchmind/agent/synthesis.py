"""Synthesis: narrate a football answer over the executed rows. No invented numbers."""

from __future__ import annotations

import json

from .. import config, llm
from .executor import ExecResult
from .types import Plan

_SYSTEM = """You are a football analyst writing the answer for PitchMind. You are given the
user's question and the EXACT result rows from a verified database query (La Liga 2015/2016).

Absolute rule: every number, name, and ranking in your answer MUST come from the provided
rows. Never invent, estimate, round beyond what's shown, or add stats that are not in the
rows. If the rows are empty, say the data returned nothing and suggest a rephrasing — do not
make up an answer.

Style: concise, plain football language, 1-3 sentences for a lookup, a short ranked list for a
leaderboard. Lead with the answer. Name the metric you're reporting. Do not mention SQL or
databases. Do not add caveats about minutes/per-90 unless the rows lack the data to answer."""


def synthesize(question: str, plan: Plan, result: ExecResult) -> str:
    rows = result.rows[: config.SYNTHESIS_TOP_N]
    payload = {
        "question": question,
        "metric": plan.metric,
        "columns": result.columns,
        "rows": rows,
        "row_count": len(result.rows),
    }
    user = (
        "Answer the question using only these rows.\n\n"
        + json.dumps(payload, default=str, ensure_ascii=False)
    )
    answer = llm.complete(_SYSTEM, user, max_tokens=700)
    assert isinstance(answer, str)
    return answer.strip()
