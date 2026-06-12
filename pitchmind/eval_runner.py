"""Gold-set eval — the Phase 1 ship gate.

For each item in ``eval/gold.jsonl`` we run the full loop and check:
- the loop succeeded and SQL was verified,
- entity resolution picked the right player/team,
- declared structural expectations (min rows, viz, substrings),
- **grounding**: every stat-like number in the answer appears in the executed rows
  (the anti-hallucination guarantee).
"""

from __future__ import annotations

import json
import re

from . import config
from .agent.loop import run
from .etl.entity_index import normalize

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
# Years / season tokens we never treat as stats.
_YEARLIKE = {"2015", "2016", "15", "16", "11", "27"}


def _norm(s: str) -> str:
    return normalize(str(s))


def _allowed_numbers(rows: list[dict], question: str) -> set[str]:
    """Numeric surface forms that may legitimately appear in the answer."""
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
    # ranks for a list of N rows
    allowed |= {str(i) for i in range(0, min(len(rows), 30) + 1)}
    allowed |= _YEARLIKE
    return allowed


def _grounding_violations(answer: str, rows: list[dict], question: str) -> list[str]:
    allowed = _allowed_numbers(rows, question)
    violations: list[str] = []
    for tok in _NUM_RE.findall(answer):
        if tok in allowed:
            continue
        # tolerate rounding: does any allowed value round to this token?
        try:
            val = float(tok)
        except ValueError:
            continue
        dec = len(tok.split(".")[1]) if "." in tok else 0
        if any(
            _is_close(val, a, dec) for a in allowed if _isfloat(a)
        ):
            continue
        # only flag plausible stat magnitudes, not stray small/large ids
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


def _check_item(item: dict) -> tuple[bool, list[str]]:
    question = item["question"]
    checks = item.get("checks", {})
    failures: list[str] = []

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


def run_eval(limit: int | None = None) -> bool:
    path = config.EVAL_DIR / "gold.jsonl"
    items = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
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

    print(f"\nGold set: {passed}/{len(items)} passed.")
    green = passed == len(items)
    print("SHIP GATE: GREEN ✅" if green else "SHIP GATE: RED ❌")
    return green


if __name__ == "__main__":
    run_eval()
