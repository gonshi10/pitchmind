---
description: Draft a {question, plan, sql} exemplar for a failing question
argument-hint: <football question that failed or was answered wrong>
allowed-tools: Bash(pitchmind:*), Bash(python -m pitchmind.cli:*), Read, Edit
---

A question failed or produced wrong SQL: "$ARGUMENTS". Turn it into a failure-driven
exemplar for `knowledge/exemplars.jsonl` (per the spec's eval loop).

1. Inspect the schema/glossary in `knowledge/` and the live views (`pitchmind` introspection)
   so the SQL references only real tables/columns.
2. Write **correct, boring, verifiable** DuckDB SQL that is read-only, filtered by
   competition + season, and `LIMIT`-capped.
3. Run it (or dry-run via the verifier) to confirm it's valid and returns sensible rows.
4. Produce the exemplar as one JSON object on a single line:
   `{"question": "...", "plan": {...}, "sql": "..."}` matching the existing entries' shape.
5. Append it to `knowledge/exemplars.jsonl` and, if useful, add the question to
   `eval/gold.jsonl` with its hand-verified expected answer.

Keep the exemplar minimal and representative of its archetype — don't over-fit to one phrasing.
