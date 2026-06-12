"""Resolve extracted entity names to ids via fuzzy matching against the alias table."""

from __future__ import annotations

from functools import lru_cache

from rapidfuzz import process, fuzz

from .. import db
from ..etl.entity_index import normalize
from .types import Entity, Plan

# Below this score we don't trust the match (rapidfuzz WRatio, 0-100).
_MIN_SCORE = 70.0
# Only entities essentially tied at the top score are broken by prominence (event count) —
# so "Suárez" resolves to the prolific Luis Suárez, not a fringe namesake — while a unique
# best match always wins outright.
_TIE_MARGIN = 0.5


@lru_cache(maxsize=2)
def _alias_table(kind: str) -> tuple[tuple[str, int, str], ...]:
    """(alias_norm, entity_id, canonical_name) rows for a kind ('player'|'team')."""
    con = db.connect(read_only=True)
    try:
        rows = con.execute(
            "SELECT alias_norm, entity_id, name FROM aliases WHERE kind = ?",
            [kind],
        ).fetchall()
        return tuple((a, int(eid), n) for a, eid, n in rows)
    finally:
        con.close()


@lru_cache(maxsize=2)
def _prominence(kind: str) -> dict[int, int]:
    """{entity_id: event_count} — used to break score ties toward the prominent entity."""
    con = db.connect(read_only=True)
    try:
        table = "players" if kind == "player" else "teams"
        id_col = "player_id" if kind == "player" else "team_id"
        rows = con.execute(f"SELECT {id_col}, events_n FROM {table}").fetchall()
        return {int(i): int(n) for i, n in rows}
    finally:
        con.close()


def resolve_entity(entity: Entity) -> Entity:
    """Attach entity_id / resolved_name / confidence (mutates and returns the entity).

    Strategy: score every alias, keep the best score per entity, then among entities within
    a small margin of the top score pick the most prominent (most events). This handles
    shared surnames and short nicknames where pure fuzzy score ties.
    """
    table = _alias_table(entity.kind)
    if not table:
        entity.note = "entity index empty — run `pitchmind etl entity-index`"
        return entity

    query = normalize(entity.text)
    choices = [row[0] for row in table]
    # All alias matches above a floor; aggregate to best score per entity.
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
    prominence = _prominence(entity.kind)
    # Among near-ties, prefer the most prominent entity.
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
        resolve_entity(entity)
    return plan
