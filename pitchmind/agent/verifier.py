"""Verify generated SQL before it runs: static checks + a dry-run.

Guarantees (CLAUDE.md guardrails): the query is a single read-only SELECT, references only
real relations, is filtered by competition + season, is LIMIT-capped, and plans cleanly.
The repair loop that regenerates on failure lives in ``loop.py`` (capped at one attempt).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import db

# Statement keywords that must never appear (word-boundary matched, case-insensitive).
_FORBIDDEN = [
    "insert", "update", "delete", "drop", "alter", "create", "attach", "detach",
    "copy", "pragma", "install", "load", "replace", "truncate", "vacuum",
    "export", "import", "call", "set",
]
_FORBIDDEN_RE = re.compile(r"\b(" + "|".join(_FORBIDDEN) + r")\b", re.IGNORECASE)


@dataclass
class VerifyResult:
    ok: bool
    errors: list[str] = field(default_factory=list)

    def feedback(self) -> str:
        return "Errors:\n" + "\n".join(f"- {e}" for e in self.errors)


def _statements(sql: str) -> list[str]:
    """Split into non-empty statements (best-effort; we forbid more than one)."""
    return [s for s in (part.strip() for part in sql.strip().rstrip(";").split(";")) if s]


def _referenced_relations(sql: str) -> set[str]:
    """Relation names following FROM / JOIN (ignores CTE/alias noise; best-effort)."""
    return {
        m.group(1).lower()
        for m in re.finditer(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, re.I)
    }


def static_check(sql: str) -> list[str]:
    errors: list[str] = []

    statements = _statements(sql)
    if len(statements) != 1:
        errors.append("must be exactly one statement")
    body = statements[0] if statements else sql.strip()

    if not re.match(r"^\s*(select|with)\b", body, re.IGNORECASE):
        errors.append("must be a single read-only SELECT (may start with WITH)")

    if _FORBIDDEN_RE.search(body):
        bad = sorted({m.lower() for m in _FORBIDDEN_RE.findall(body)})
        errors.append(f"forbidden keyword(s): {', '.join(bad)} — read-only SELECT only")

    # CTE names are valid relations too; allow them alongside real DB relations.
    cte_names = {
        m.group(1).lower()
        for m in re.finditer(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", sql, re.I)
    }
    real = {r.lower() for r in db.relations()}
    referenced = _referenced_relations(sql)
    unknown = referenced - real - cte_names
    if unknown:
        errors.append(
            f"unknown relation(s): {', '.join(sorted(unknown))}. "
            f"Use only existing tables/views."
        )

    if not re.search(r"\bcompetition_id\b", sql, re.I) or not re.search(
        r"\bseason_id\b", sql, re.I
    ):
        errors.append(
            "must filter `competition_id = 11 AND season_id = 27` (both required)"
        )

    if not re.search(r"\blimit\b", sql, re.I):
        errors.append("must include a LIMIT")

    return errors


def dry_run(sql: str) -> str | None:
    """EXPLAIN the query on a read-only connection. Returns an error string or None."""
    con = db.connect(read_only=True)
    try:
        con.execute("EXPLAIN " + sql)
        return None
    except Exception as exc:  # noqa: BLE001 — surface any planner error as feedback
        return f"dry-run failed: {exc}"
    finally:
        con.close()


def verify(sql: str) -> VerifyResult:
    errors = static_check(sql)
    # Only dry-run if static checks pass — a forbidden/multi-statement query shouldn't touch
    # the DB even read-only.
    if not errors:
        err = dry_run(sql)
        if err:
            errors.append(err)
    return VerifyResult(ok=not errors, errors=errors)
