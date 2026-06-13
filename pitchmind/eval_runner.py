"""Gold-set eval — the Phase 1 ship gate (core) and optional breadth set."""

from __future__ import annotations

import json
import re

from . import config
from .agent.loop import run
from .etl import catalog
from .etl.entity_index import normalize

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _norm(s: str) -> str:
    return normalize(str(s))


def _yearlike_tokens() -> set[str]:
    """Season/year tokens that may appear in answers without being stats."""
    tokens: set[str] = set()
    for target in catalog.loaded_targets():
        for part in target.season_name.replace("/", " ").split():
            tokens.add(part)
        tokens.add(str(target.competition_id))
        tokens.add(str(target.season_id))
    for year in range(1950, 2035):
        tokens.add(str(year))
        tokens.add(str(year % 100))
    return tokens


def _allowed_numbers(rows: list[dict], question: str) -> set[str]:
    allowed: set[str] = set()
    for row in rows:
        for v in row.values():
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, (int, float)):
                f = float(v)
                allowed.add(str(int(f)) if f == int(f) else str(f))
                allowed.add(f"{f:.1f}")
                allowed.add(f"{f:.2f}")
                allowed.add(str(round(f)))
            else:
                for m in _NUM_RE.findall(str(v)):
                    allowed.add(m)
    allowed |= set(_NUM_RE.findall(question))
    allowed |= {str(i) for i in range(0, min(len(rows), 30) + 1)}
    allowed.add(str(len(rows)))
    allowed |= _yearlike_tokens()
    return allowed


def _grounding_violations(answer: str, rows: list[dict], question: str) -> list[str]:
    allowed = _allowed_numbers(rows, question)
    violations: list[str] = []
    for tok in _NUM_RE.findall(answer):
        if tok in allowed:
            continue
        try:
            val = float(tok)
        except ValueError:
            continue
        dec = len(tok.split(".")[1]) if "." in tok else 0
        if any(_is_close(val, a, dec) for a in allowed if _isfloat(a)):
            continue
        if 2 <= val <= 1000:
            violations.append(tok)
    return violations


def _isfloat(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _is_close(val: float, other: str, dec: int) -> bool:
    return round(float(other), dec) == round(val, dec)


def _target_loaded(competition_id: int, season_id: int) -> bool:
    loaded = catalog.loaded_targets()
    return any(
        t.competition_id == competition_id and t.season_id == season_id for t in loaded
    )


def _check_item(item: dict) -> tuple[bool, list[str]]:
    question = item["question"]
    checks = item.get("checks", {})
    failures: list[str] = []

    req = checks.get("requires_target")
    if req:
        cid, sid = int(req["competition_id"]), int(req["season_id"])
        if not _target_loaded(cid, sid):
            failures.append(
                f"skipped: target competition_id={cid} season_id={sid} not loaded"
            )
            return False, failures

    result = run(question)
    if not result.ok:
        return False, [f"loop did not succeed: {result.answer}"]

    if "min_rows" in checks and len(result.rows) < checks["min_rows"]:
        failures.append(f"min_rows: got {len(result.rows)} < {checks['min_rows']}")

    if checks.get("expect_viz") and not result.viz_path:
        failures.append("expect_viz: no viz produced")

    for name in checks.get("entities_resolved", []):
        ents = result.trace["stages"]["plan"]["entities"]
        matched = any(
            e["entity_id"] is not None
            and _norm(name) in _norm(e["resolved_name"] or "")
            for e in ents
        )
        if not matched:
            failures.append(f"entity not resolved: {name} (got {ents})")

    contains = checks.get("answer_contains_any")
    if contains:
        ans = _norm(result.answer)
        if not any(_norm(s) in ans for s in contains):
            failures.append(f"answer missing any of {contains}")

    grounding = _grounding_violations(result.answer, result.rows, question)
    if grounding:
        failures.append(f"ungrounded numbers in answer: {grounding}")

    return (not failures), failures


def run_eval(gold_file: str = "gold_core.jsonl", limit: int | None = None) -> bool:
    path = config.EVAL_DIR / gold_file
    items = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if limit:
        items = items[:limit]

    passed = 0
    for i, item in enumerate(items, start=1):
        ok, failures = _check_item(item)
        status = "PASS" if ok else "FAIL"
        print(f"[{i}/{len(items)}] {status}  {item['question']}")
        for f in failures:
            print(f"        - {f}")
        passed += int(ok)

    print(f"\nGold set ({gold_file}): {passed}/{len(items)} passed.")
    green = passed == len(items)
    print("SHIP GATE: GREEN ✅" if green else "SHIP GATE: RED ❌")
    return green


if __name__ == "__main__":
    run_eval()
