"""Execute verified SQL on a read-only connection, with a row cap and wall-clock timeout.

The row cap is enforced by wrapping the query in an outer LIMIT (independent of whatever
LIMIT the model wrote), and the timeout by running the query in a worker thread and calling
``interrupt()`` if it overruns. DuckDB has no native statement timeout.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .. import config, db


class ExecutionError(RuntimeError):
    pass


@dataclass
class ExecResult:
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)


def execute(sql: str) -> ExecResult:
    capped = f"SELECT * FROM (\n{sql.rstrip().rstrip(';')}\n) AS _capped LIMIT {config.ROW_CAP}"
    con = db.connect(read_only=True)

    box: dict[str, object] = {}

    def run() -> None:
        try:
            cur = con.execute(capped)
            box["columns"] = [d[0] for d in cur.description]
            box["rows"] = cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=config.STATEMENT_TIMEOUT_S)

    if worker.is_alive():
        con.interrupt()
        worker.join(timeout=2)
        con.close()
        raise ExecutionError(
            f"query exceeded the {config.STATEMENT_TIMEOUT_S}s budget"
        )

    try:
        if "error" in box:
            raise ExecutionError(str(box["error"]))
        columns = box.get("columns", [])  # type: ignore[assignment]
        raw_rows = box.get("rows", [])  # type: ignore[assignment]
        rows = [dict(zip(columns, r)) for r in raw_rows]  # type: ignore[arg-type]
        return ExecResult(columns=list(columns), rows=rows)  # type: ignore[arg-type]
    finally:
        con.close()
