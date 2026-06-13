"""FastAPI service exposing the PitchMind agent.

Thin transport over ``pitchmind.agent.loop.run`` — no analysis logic lives here.

Endpoints:
- GET  /health            — liveness + whether the DB is built
- GET  /ask/stream?question= — SSE: live pipeline stages, then a final `result`, then `done`
- POST /ask               — non-streaming JSON (full result + trace); for curl/tests
- GET  /trace/{run_id}    — the persisted trace JSON
- GET  /viz/{filename}    — serve a shot-map PNG from the data dir
"""

from __future__ import annotations

import json
import os
import queue
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from pitchmind import config, trace_store
from pitchmind.agent.loop import run as run_agent
from pitchmind.agent.types import AgentResult

app = FastAPI(title="PitchMind", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _viz_url(result: AgentResult) -> str | None:
    if not result.viz_path:
        return None
    return f"/viz/{os.path.basename(result.viz_path)}"


def _result_payload(result: AgentResult) -> dict:
    """Compact result for the client (rows capped; viz as a URL)."""
    return {
        "run_id": result.run_id,
        "ok": result.ok,
        "answer": result.answer,
        "sql": result.sql,
        "columns": result.columns,
        "rows": result.rows[:50],
        "row_count": len(result.rows),
        "viz_url": _viz_url(result),
        "elapsed_s": result.trace.get("elapsed_s"),
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "db_present": config.DB_PATH.exists(),
        "target": config.TARGET.label,
    }


@app.get("/ask/stream")
def ask_stream(question: str) -> StreamingResponse:
    """Stream the agent's pipeline stages as Server-Sent Events.

    The loop is synchronous and blocking, so it runs in a worker thread and pushes events
    onto a queue that this generator drains. The terminal `result` and `done` events are
    emitted by the API once the loop returns.
    """
    events: "queue.Queue[tuple[str, str, dict]]" = queue.Queue()
    SENTINEL = ("__sentinel__", "", {})

    def on_event(stage: str, data: dict) -> None:
        events.put(("stage", stage, data))

    def worker() -> None:
        try:
            result = run_agent(question, on_event=on_event)
            events.put(("final", "result", _result_payload(result)))
        except Exception as exc:  # noqa: BLE001 — surface any failure to the client
            events.put(("final", "agent_error", {"message": str(exc)}))
        finally:
            events.put(SENTINEL)

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        while True:
            kind, event, data = events.get()
            if kind == "__sentinel__":
                yield _sse("done", {})
                break
            # The loop's stage-level "error" is renamed so it doesn't collide with the
            # browser EventSource's native "error" event.
            yield _sse("agent_error" if event == "error" else event, data)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class AskBody(BaseModel):
    question: str


@app.post("/ask")
def ask(body: AskBody) -> JSONResponse:
    try:
        result = run_agent(body.question)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))
    payload = _result_payload(result)
    payload["trace"] = result.trace
    return JSONResponse(payload)


@app.get("/trace/{run_id}")
def get_trace(run_id: str) -> JSONResponse:
    trace = trace_store.load(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return JSONResponse(trace)


@app.get("/viz/{filename}")
def get_viz(filename: str) -> FileResponse:
    safe = os.path.basename(filename)
    if not safe.endswith(".png"):
        raise HTTPException(status_code=400, detail="only .png is served")
    path = config.DATA_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(path, media_type="image/png")
