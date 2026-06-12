"""Orchestrate the full agent loop and assemble the trace.

plan -> resolve -> retrieve(cached) -> generate SQL -> verify (one repair loop) ->
execute (read-only, capped) -> viz -> synthesize. Every stage is recorded in the trace,
which is both the debugger and the showcase artifact.
"""

from __future__ import annotations

import time

from .. import config
from . import planner, resolve, sql_gen, synthesis, verifier, viz
from .executor import ExecutionError, execute
from .types import AgentResult


def _entity_trace(plan) -> list[dict]:
    return [
        {
            "text": e.text,
            "kind": e.kind,
            "entity_id": e.entity_id,
            "resolved_name": e.resolved_name,
            "confidence": e.confidence,
            "note": e.note,
        }
        for e in plan.entities
    ]


def run(question: str) -> AgentResult:
    t0 = time.time()
    trace: dict = {"question": question, "stages": {}}

    # 1-2. Plan + resolve entities.
    plan = planner.plan(question)
    resolve.resolve(plan)
    trace["stages"]["plan"] = {
        "question_type": plan.question_type,
        "metric": plan.metric,
        "wants_viz": plan.wants_viz,
        "viz_type": plan.viz_type,
        "entities": _entity_trace(plan),
    }

    # 3-6. Generate SQL and verify, with at most one repair (config.MAX_REPAIRS).
    attempts: list[dict] = []
    sql = sql_gen.generate(question, plan)
    result_v = verifier.verify(sql)
    attempts.append({"sql": sql, "errors": result_v.errors})

    repairs = 0
    while not result_v.ok and repairs < config.MAX_REPAIRS:
        repairs += 1
        sql = sql_gen.generate(question, plan, repair=result_v.feedback())
        result_v = verifier.verify(sql)
        attempts.append({"sql": sql, "errors": result_v.errors})

    trace["stages"]["sql"] = {"final": sql, "attempts": attempts, "repairs": repairs}

    if not result_v.ok:
        trace["elapsed_s"] = round(time.time() - t0, 2)
        return AgentResult(
            answer=(
                "I couldn't compute that reliably — the query didn't pass verification. "
                "Try rephrasing, or ask for a simpler breakdown."
            ),
            sql=sql,
            ok=False,
            trace=trace,
        )

    # 7. Execute (read-only, capped, timed).
    try:
        exec_result = execute(sql)
    except ExecutionError as exc:
        trace["stages"]["execute"] = {"error": str(exc)}
        trace["elapsed_s"] = round(time.time() - t0, 2)
        return AgentResult(
            answer=f"I couldn't run that query: {exc}",
            sql=sql,
            ok=False,
            trace=trace,
        )

    trace["stages"]["execute"] = {
        "columns": exec_result.columns,
        "row_count": len(exec_result.rows),
        "rows_preview": exec_result.rows[:10],
    }

    # 8. Viz (shot map only in Phase 1).
    viz_title = plan.entities[0].resolved_name if plan.entities else ""
    viz_path = viz.maybe_render(plan, exec_result, title=viz_title)
    if viz_path:
        trace["stages"]["viz"] = {"path": viz_path}

    # 9. Synthesize over the actual rows.
    answer = synthesis.synthesize(question, plan, exec_result)
    trace["stages"]["synthesis"] = {"answer": answer}
    trace["elapsed_s"] = round(time.time() - t0, 2)

    return AgentResult(
        answer=answer,
        sql=sql,
        rows=exec_result.rows,
        columns=exec_result.columns,
        viz_path=viz_path,
        ok=True,
        trace=trace,
    )
