# PitchMind — project memory

Natural-language football analytics agent over StatsBomb open event data. Ask in plain
English → the agent plans, writes verifiable DuckDB SQL, runs it read-only, reasons over the
result rows, and answers in football language with a pitch viz. The repo's real purpose is to
**showcase agentic LLM systems engineering** (tool-use loop, verification, anti-hallucination,
observability) — the credibility is in the loop, not a chat wrapper.

Full spec: @docs/SPEC.md

## Phase discipline
**Ship Phase 1 before anything else. Don't gold-plate.** Phase 1 = La Liga 2015/16 only, ~6
question archetypes, the full loop end-to-end, one viz (shot map with xG), a CLI. No web UI
(Phase 2), no critic subagent / caching / extra competitions (Phase 3+) until the slice ships.

**Current phase: Phase 0 → Phase 1.**

## Hard guardrails (load-bearing — do not violate)
- Every query is **read-only**, **filtered** (competition + season), and **`LIMIT`-capped**.
- **Synthesis must never output a number that is not present in the executed result rows.**
  Numbers are computed, never generated.
- Verification is mandatory **before** execution: every table/column referenced must exist,
  a competition/season filter must be present, a `LIMIT` must be present, then dry-run.
- Max **1** SQL repair loop and **1** critic bounce. No unbounded agent recursion.
- Keep the **trace** complete (question → plan → entities → context → SQL → rows → answer).
- Never embed raw event rows. Retrieval is only the three small corpora (schema / glossary /
  exemplars). They live in `knowledge/` and, in Phase 1, are inlined into the cached prefix.

## LLM conventions
- Model: `claude-opus-4-8`. Adaptive thinking: `thinking={"type": "adaptive"}` —
  **never** `budget_tokens` (it 400s on this model).
- Cache the static schema/glossary/few-shot prefix with `cache_control={"type": "ephemeral"}`
  on the last system block.
- Strict JSON via `output_config={"format": {"type": "json_schema", ...}}` (planner, plans).
- **One Anthropic call site:** `pitchmind/llm.py`. Don't scatter API calls.
- **Consult the `/claude-api` skill before writing Anthropic calls — don't hand-roll from
  memory.** Model IDs, caching, thinking, and structured-output syntax come from there.

## Code conventions
- Prefer **boring, verifiable SQL** over clever pandas.
- DuckDB for analytics; Postgres only for app state later (not Phase 1).
- StatsBomb attribution must stay in `README.md` and any app footer (required by their license).
- `data/` is rebuilt by ETL and gitignored — never commit `.duckdb`/parquet/PNGs.

## Key commands
```
pitchmind etl download | flatten | load-duckdb | entity-index | marts
pitchmind ask "…"            # add --show-sql / --show-trace
pitchmind eval               # runs eval/gold.jsonl — the Phase 1 ship gate
```
Env: `python -m venv .venv && source .venv/bin/activate && pip install -e .`;
`ANTHROPIC_API_KEY` in `.env` (gitignored).
