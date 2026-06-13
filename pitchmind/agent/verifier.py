"""Verify generated SQL before it runs: static checks + a dry-run."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import db
from ..etl import catalog
from .types import Scope

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
    return [s for s in (part.strip() for part in sql.strip().rstrip(";").split(";")) if s]


def _referenced_relations(sql: str) -> set[str]:
    return {
        m.group(1).lower()
        for m in re.finditer(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, re.I)
    }


def _where_clause(sql: str) -> str:
    """Best-effort extraction of the outer WHERE clause."""
    match = re.search(
        r"\bwhere\b(.*?)(?:\bgroup\b|\border\b|\blimit\b|\bhaving\b|$)",
        sql,
        re.I | re.S,
    )
    return match.group(1) if match else ""


def _scope_ids_in_where(where: str, competition_id: int, season_id: int) -> bool:
    comp_ok = re.search(
        rf"\bcompetition_id\s*=\s*{competition_id}\b",
        where,
        re.I,
    ) or re.search(
        rf"\bcompetition_id\s+in\s*\([^)]*\b{competition_id}\b",
        where,
        re.I,
    )
    season_ok = re.search(
        rf"\bseason_id\s*=\s*{season_id}\b",
        where,
        re.I,
    ) or re.search(
        rf"\bseason_id\s+in\s*\([^)]*\b{season_id}\b",
        where,
        re.I,
    )
    return bool(comp_ok and season_ok)


def static_check(sql: str, scope: Scope | None = None) -> list[str]:
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

    where = _where_clause(sql)
    if not where:
        errors.append(
            "must include a WHERE clause filtering competition_id and season_id"
        )
    elif "competition_id" not in where.lower() or "season_id" not in where.lower():
        errors.append(
            "WHERE clause must filter both competition_id and season_id"
        )

    if scope and where:
        if not _scope_ids_in_where(where, scope.competition_id, scope.season_id):
            errors.append(
                f"must filter competition_id = {scope.competition_id} "
                f"AND season_id = {scope.season_id} in WHERE"
            )

    loaded = catalog.loaded_targets()
    if loaded and where:
        for target in loaded:
            if _scope_ids_in_where(where, target.competition_id, target.season_id):
                break
        else:
            allowed = ", ".join(
                f"({t.competition_id}, {t.season_id})" for t in loaded[:5]
            )
            errors.append(
                f"competition_id/season_id filter must match a loaded target: {allowed}"
            )

    if not re.search(r"\blimit\b", sql, re.I):
        errors.append("must include a LIMIT")

    return errors


def dry_run(sql: str) -> str | None:
    con = db.connect(read_only=True)
    try:
        con.execute("EXPLAIN " + sql)
        return None
    except Exception as exc:  # noqa: BLE001
        return f"dry-run failed: {exc}"
    finally:
        con.close()


def verify(sql: str, scope: Scope | None = None) -> VerifyResult:
    errors = static_check(sql, scope=scope)
    if not errors:
        err = dry_run(sql)
        if err:
            errors.append(err)
    return VerifyResult(ok=not errors, errors=errors)
