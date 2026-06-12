---
description: Run the gold-set eval and report green/red against the Phase 1 ship gate
allowed-tools: Bash(pitchmind:*), Bash(python -m pitchmind.cli:*)
---

Run `pitchmind eval` (the `eval/gold.jsonl` gold set) and report the result against the
**Phase 1 ship gate**.

The gate is green only when, for every gold item:
- the generated SQL passes the verifier (tables/columns real, filter present, LIMIT present),
- entity resolution picks the right player/team,
- the numbers in the answer match the executed rows,
- no stat was invented.

Report pass/fail per item and the overall verdict. For each failure, show the question, the
generated SQL, and what diverged — then propose the fix (usually a new exemplar via
`/new-exemplar`, occasionally a glossary or schema-doc clarification). **Phase 1 is not
shippable until this is green.**
