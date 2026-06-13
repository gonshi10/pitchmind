"""Resolve extracted entity names to ids via fuzzy matching against the alias table."""

from __future__ import annotations

from functools import lru_cache

from rapidfuzz import process, fuzz

from .. import db
from ..etl.entity_index import normalize
from .types import Entity, Plan, Scope

_MIN_SCORE = 70.0
_TIE_MARGIN = 0.5


@lru_cache(maxsize=16)
def _alias_table(
    kind: str,
    competition_id: int | None,
    season_id: int | None,
) -> tuple[tuple[str, int, str], ...]:
    """(alias_norm, entity_id, canonical_name) rows for a kind, optionally scoped."""
    con = db.connect(read_only=True)
    try:
        if competition_id is not None and season_id is not None:
            rows = con.execute(
                """
                SELECT alias_norm, entity_id, name FROM aliases
                WHERE kind = ?
                  AND (competition_id IS NULL
                       OR (competition_id = ? AND season_id = ?))
                """,
                [kind, competition_id, season_id],
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT alias_norm, entity_id, name FROM aliases WHERE kind = ?",
                [kind],
            ).fetchall()
        return tuple((a, int(eid), n) for a, eid, n in rows)
    finally:
        con.close()


@lru_cache(maxsize=16)
def _prominence(
    kind: str,
    competition_id: int | None,
    season_id: int | None,
) -> dict[int, int]:
    con = db.connect(read_only=True)
    try:
        if kind == "player":
            if competition_id is not None and season_id is not None:
                rows = con.execute(
                    """
                    SELECT player_id, events_n FROM players
                    WHERE competition_id = ? AND season_id = ?
                    """,
                    [competition_id, season_id],
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT player_id, events_n FROM players"
                ).fetchall()
            return {int(i): int(n) for i, n in rows}
        if competition_id is not None and season_id is not None:
            rows = con.execute(
                """
                SELECT team_id, events_n FROM teams
                WHERE competition_id = ? AND season_id = ?
                """,
                [competition_id, season_id],
            ).fetchall()
        else:
            rows = con.execute("SELECT team_id, events_n FROM teams").fetchall()
        return {int(i): int(n) for i, n in rows}
    finally:
        con.close()


def resolve_entity(entity: Entity, scope: Scope | None = None) -> Entity:
    comp_id = scope.competition_id if scope else None
    season_id = scope.season_id if scope else None
    table = _alias_table(entity.kind, comp_id, season_id)
    if not table:
        entity.note = "entity index empty — run `pitchmind etl entity-index`"
        return entity

    query = normalize(entity.text)
    choices = [row[0] for row in table]
    matches = process.extract(query, choices, scorer=fuzz.WRatio, limit=50)
    best_by_entity: dict[int, tuple[float, str]] = {}
    for _, score, idx in matches:
        _, entity_id, name = table[idx]
        prev = best_by_entity.get(entity_id)
        if prev is None or score > prev[0]:
            best_by_entity[entity_id] = (float(score), name)

    if not best_by_entity:
        entity.note = f"no candidate for '{entity.text}'"
        return entity

    top_score = max(s for s, _ in best_by_entity.values())
    prominence = _prominence(entity.kind, comp_id, season_id)
    contenders = [
        (eid, score, name)
        for eid, (score, name) in best_by_entity.items()
        if score >= top_score - _TIE_MARGIN
    ]
    entity_id, score, name = max(
        contenders, key=lambda c: (prominence.get(c[0], 0))
    )

    entity.entity_id = entity_id
    entity.resolved_name = name
    entity.confidence = float(score)
    if score < _MIN_SCORE:
        entity.note = (
            f"low-confidence match for '{entity.text}' -> '{name}' ({score:.0f})"
        )
    return entity


def resolve(plan: Plan) -> Plan:
    """Resolve every entity in the plan in place."""
    for entity in plan.entities:
        resolve_entity(entity, plan.scope)
    return plan
