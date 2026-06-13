"""Resolve question time scope to competition_id + season_id."""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from .. import config
from ..etl import catalog
from ..etl.entity_index import normalize
from .types import Plan, Scope


@dataclass
class ScopeResult:
    scope: Scope | None = None
    error: str | None = None


def _loaded_targets() -> list[config.Target]:
    loaded = catalog.loaded_targets()
    if loaded:
        return loaded
    return [config.DEFAULT_TARGET]


def _match_loaded_label(text: str, loaded: list[config.Target]) -> Scope | None:
    labels = [t.label for t in loaded]
    result = process.extractOne(text, labels, scorer=fuzz.WRatio)
    if result is None:
        return None
    label, score, idx = result
    if score < 65:
        return None
    target = loaded[idx]
    return Scope(
        competition_id=target.competition_id,
        season_id=target.season_id,
        label=target.label,
        confidence=float(score),
    )


def _match_from_db(text: str) -> Scope | None:
    """Fuzzy match against seasons table in DuckDB if available."""
    if not config.DB_PATH.exists():
        return None
    try:
        from .. import db

        con = db.connect(read_only=True)
        try:
            rows = con.execute(
                "SELECT competition_id, season_id, label FROM seasons"
            ).fetchall()
        finally:
            con.close()
    except (FileNotFoundError, Exception):  # noqa: BLE001
        return None

    if not rows:
        return None

    labels = [str(r[2]) for r in rows]
    result = process.extractOne(text, labels, scorer=fuzz.WRatio)
    if result is None or result[1] < 65:
        return None
    idx = labels.index(result[0])
    comp_id, season_id, label = rows[idx]
    loaded = _loaded_targets()
    if not any(
        t.competition_id == int(comp_id) and t.season_id == int(season_id)
        for t in loaded
    ):
        return None
    return Scope(
        competition_id=int(comp_id),
        season_id=int(season_id),
        label=str(label),
        confidence=float(result[1]),
    )


def resolve_scope(question: str, plan: Plan) -> ScopeResult:
    """Map planner time_scope + question text to a loaded competition/season."""
    loaded = _loaded_targets()
    if not loaded:
        return ScopeResult(
            error=(
                "No competition data is loaded. Run `pitchmind etl add` "
                "(e.g. `pitchmind etl add --name 'La Liga 2015/16'`)."
            )
        )

    # Single loaded target — use it when scope is unspecified or matches default.
    if len(loaded) == 1:
        target = loaded[0]
        scope = Scope(
            competition_id=target.competition_id,
            season_id=target.season_id,
            label=target.label,
            confidence=100.0,
        )
        return ScopeResult(scope=scope)

    candidates: list[Scope] = []
    for text in (plan.time_scope, question):
        if not text:
            continue
        hit = _match_from_db(text) or _match_loaded_label(text, loaded)
        if hit:
            candidates.append(hit)

    if not candidates:
        labels = ", ".join(t.label for t in loaded[:8])
        more = f" (+{len(loaded) - 8} more)" if len(loaded) > 8 else ""
        return ScopeResult(
            error=(
                f"I couldn't tell which competition/season you mean. "
                f"Loaded data includes: {labels}{more}. "
                "Name the league and season in your question."
            )
        )

    best = max(candidates, key=lambda s: s.confidence or 0)
    ambiguous = [
        c for c in candidates
        if c.label != best.label
        and (c.confidence or 0) >= (best.confidence or 0) - 5
    ]
    if ambiguous:
        options = ", ".join({c.label for c in ambiguous + [best]})
        best.note = f"ambiguous scope; other candidates: {options}"
    return ScopeResult(scope=best)
