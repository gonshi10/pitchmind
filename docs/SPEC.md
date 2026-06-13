# PitchMind — Build Spec

> A natural-language football analytics agent over StatsBomb open event data.
> Ask in plain English → the agent plans, writes SQL, verifies it, executes, reasons over
> the result, and returns a written answer plus a pitch visualization.
>
> This document is the full source of truth. The concise project memory in `CLAUDE.md`
> imports it. Build in the phases at the bottom. Ship Phase 1 end-to-end before touching
> Phase 2. Do not gold-plate.

## 0. What we're building and why it matters

PitchMind turns questions like *"which midfielders progressed the ball most under pressure
in La Liga 2015/16?"* into a real analysis: the agent resolves the entities, generates
verifiable SQL against flattened event data, runs it in a sandbox, and answers in plain
football language with a pass map / shot map / heatmap where it helps.

The showcase intent is explicit: this repo demonstrates **agentic LLM systems engineering**
(tool-use loops, verification, subagents, retrieval, caching, observability) using football
as the domain that proves the system can reason over messy, real-world structured data. The
domain credibility comes from seeding it with sharp, footballer-grade questions. The
engineering credibility comes from the loop, not from a chat wrapper.

## 1. Core design decisions (don't re-litigate mid-build)

1. **DuckDB for analytics, not Postgres.** Read-only analytical scans over event tables.
   DuckDB is embedded, columnar, queries parquet directly, zero-ops. Postgres/Supabase is
   used *only* for app state (saved questions, run traces, history) if/when the web app
   needs persistence — never for analytics queries.
2. **Text-to-SQL, not text-to-pandas.** SQL is easier to sandbox (read-only connection),
   validate (parse, check tables/columns exist), and the model is excellent at it.
3. **RAG is narrow.** Retrieval covers exactly three corpora: (a) **schema docs** — columns
   + semantics per event type; (b) **metric glossary** — definitions mapping fuzzy football
   language ("progressive pass", "field tilt", "PPDA", "ball progression under pressure") to
   concrete computations; (c) **few-shot exemplars** — past question→SQL pairs. We **never**
   embed raw event rows. They live in DuckDB and get queried.
4. **Verification is a first-class step.** Every generated query passes a static check (real
   tables/columns, has the right competition/season filter, has a row limit) and a dry-run
   before it executes. One capped repair loop on failure.
5. **Numbers are computed, never generated.** The synthesis LLM only narrates over the
   *actual* result rows passed back to it. Forbidden from inventing stats. Enforced in the
   system prompt and checked in eval.
6. **Prompt caching on the static prefix.** Schema + glossary + few-shots are a large, stable
   prefix → cache it with `cache_control` on the Anthropic API.

## 2. Architecture

```
Web App (Next.js) — Phase 2+
  chat UI · answer + viz · "show the SQL" · expandable agent trace
        │ HTTP (question, context)
        ▼
Agent service (Python)
  planner (intent + entity res)
  retrieval (schema + glossary + few-shots, cached prefix)
  sql_gen (DuckDB SQL)
  verifier (static check + dry-run + one repair)
  executor (read-only DuckDB, timeout, row cap)
  viz router (mplsoccer)
  synthesis (narrate over rows)
  critic subagent (football sanity) — Phase 3
  observability (full trace persisted)
        │
        ▼
Data layer (offline ETL, run once / on refresh)
  StatsBomb JSON → flatten events → Parquet → DuckDB
  build entity index · materialize metric marts
  (RAG corpora are static files — no event rows embedded)
```

**Components**
- **Planner:** classifies question type, resolves entities (player, team, competition,
  season) against the entity index with fuzzy matching. Returns a structured plan.
- **Retrieval:** pulls the schema slice, metric definitions, and few-shot exemplars.
- **SQL gen:** DuckDB SQL grounded in the retrieved schema + glossary + exemplars (cached prefix).
- **Verifier:** parses SQL, asserts every referenced table/column exists, asserts a
  competition/season filter is present, asserts a `LIMIT`, then dry-runs. One repair attempt.
- **Executor:** runs verified SQL on a **read-only** DuckDB connection with a statement
  timeout and row cap.
- **Viz router:** decides whether a visual helps and which template (pass map, shot map w/
  xG, heatmap, pass network, progression map). Renders with mplsoccer → PNG/SVG.
- **Synthesis:** writes the football-language answer over the actual rows. No invented numbers.
- **Critic subagent (Phase 3):** cheap second pass checking football sense; can bounce once.
- **Observability:** every run persists a full trace; surfaced in the UI as an expandable panel.

## 3. The agent loop

1. **Intake** — question + optional conversation context.
2. **Plan** — classify question type, extract candidate entities and time scope, decide if a
   viz is wanted. Output strict JSON.
3. **Resolve entities** — fuzzy-match names against the entity index (`rapidfuzz`). Ambiguous
   → top candidate with a confidence note, or one disambiguating question. Resolve "15/16",
   "last season", "the WC final" to concrete ids.
4. **Retrieve** — assemble the cached prefix (schema + glossary + exemplars).
5. **Generate SQL** — cached prefix + resolved plan → DuckDB SQL only.
6. **Verify** — static checks (tables/columns real, filters present, LIMIT present) → dry-run.
   On error, **one** repair loop. Still failing → graceful "couldn't compute reliably" + trace.
7. **Execute** — read-only connection, timeout, row cap. Get result rows.
8. **Route viz** — if applicable, map result → mplsoccer template → render image.
9. **Synthesize** — narrate over the actual rows. Numbers come only from the rows.
10. **Critique** — subagent sanity-checks; bounce once if it flags something concrete (Phase 3).
11. **Return** — answer + viz + full trace. Persist the trace.

**Caps:** max 1 repair loop, max 1 critic bounce, hard wall-clock budget per request, row cap
on every query.

## 4. RAG & efficiency

**Retrieval corpora (the only things we embed — and in Phase 1 we inline rather than embed):**
- **Schema docs** — one short doc per event type (pass, shot, carry, pressure, duel, dribble,
  interception, …) listing columns and meaning. Keeps the model from hallucinating columns.
- **Metric glossary** — football language → computation. e.g. *progressive pass* = forward
  pass moving the ball ≥ X meters toward goal / into the final third; *under pressure* = the
  StatsBomb `under_pressure` flag; *field tilt*, *PPDA*, *xG*, *xT*, *pass into box*.
- **Few-shot exemplars** — curated `(question, plan, SQL)` triples covering each archetype.
  Highest-leverage; grow as failures are found.

**Efficiency layers**
- **Prompt caching (Anthropic):** schema + glossary + few-shots = a large stable prefix →
  `cache_control`. Cuts cost and latency on every request.
- **Metric marts:** pre-materialize common aggregations (player-season summaries, progressive
  passes, xG totals, shot tables) at ETL time. Most questions hit a mart instead of scanning
  raw events.
- **Semantic cache (Phase 3):** embed incoming questions; reuse plan/SQL above a similarity
  threshold. Data is static so results can be cached too (key = normalized SQL).
- **Token discipline:** never put raw rows into synthesis beyond a small top-N; aggregate first.
- **Embeddings:** a local sentence-transformer (e.g. MiniLM) is fine when retrieval is added;
  the vector store can be DuckDB VSS or a small local index — no separate vector DB service.

## 5. Data pipeline (ETL)

Source: **StatsBomb Open Data** (`github.com/statsbomb/open-data`), via `statsbombpy`. Free
competitions include the Messi-era La Liga, men's & women's World Cups, Champions League
finals, and more.

> **Attribution:** StatsBomb open data requires attribution and acceptance of their user
> agreement. Keep the credit line in the README and the app footer.

Steps:
1. `sb.competitions()` → pick target competitions/seasons (start with La Liga 2015/16 only).
2. For each match: `sb.events(match_id)` → flatten nested fields (`location` → `x`,`y`;
   shot/pass/carry sub-objects → columns; end locations; `under_pressure`; xG).
3. Write flattened events to partitioned parquet (by competition/season/match).
4. Load parquet into a DuckDB file; create typed views per event type.
5. Build the **entity index**: players, teams, competitions, seasons + alias table
   (nicknames, short names, accent-stripped variants).
6. Build **metric marts** (player-season agg, progressive actions, shot tables).
7. Build the **RAG store**: schema docs, glossary, exemplars (static files in Phase 1).

All of this is a CLI (`pitchmind etl …`), idempotent, re-runnable when adding competitions.

## 6. Product flow

**User journey:** ask → answer + viz → follow-up (context-aware) → "show the SQL" / "show the
trace" disclosure → export/share the viz.

**Two audiences, one engine:** analyst/scout mode (StatsBomb literacy, exposes SQL + metric
definitions, dense output) and fan/media mode (plain language, viz-forward, no jargon).

**Value narrative:** the analytical brain that turns raw event data into scouting-grade answers
in seconds. Monetization framing (narrative only): clubs/agencies pay for seat access + custom
competitions; media pays for fan-facing embeds. Keep proprietary scouting IP out of the open repo.

## 7. Tech stack & repo structure

**Stack:** Python 3.11+, FastAPI (Phase 2+), DuckDB, `statsbombpy`, `mplsoccer`, `rapidfuzz`,
Anthropic Claude API (with prompt caching), a local embedding model (when retrieval is added),
Next.js/React + Tailwind front end (Phase 2+). Optional: Supabase/Postgres for app state,
Langfuse or structured JSON logging for traces. Deploy on Railway.

```
pitchmind/
├── CLAUDE.md            # concise project memory (imports docs/SPEC.md)
├── docs/SPEC.md         # this file
├── README.md            # showcase framing + StatsBomb attribution
├── pyproject.toml
├── .claude/             # Claude Code project config (settings, commands, agents)
├── data/                # raw/ parquet/ pitchmind.duckdb  (gitignored)
├── pitchmind/
│   ├── config.py        # paths, model id, competition/season constants
│   ├── db.py            # read-only DuckDB connection + schema introspection
│   ├── llm.py           # Anthropic wrapper (cached prefix, JSON parse)
│   ├── etl/             # flatten · load_duckdb · entity_index · marts
│   ├── agent/           # planner · resolve · retrieval · sql_gen · verifier
│   │                    #   · executor · viz · synthesis · loop
│   └── cli.py           # `pitchmind etl …` and `pitchmind ask …`
├── knowledge/           # schema_docs.md · glossary.md · exemplars.jsonl
├── api/                 # FastAPI (Phase 2+): /ask, /trace/{id}, /health
├── web/                 # Next.js app (Phase 2+)
├── eval/                # gold.jsonl + run_eval.py
└── tests/
```

## 8. Build phases (ship in order — do not skip ahead)

- **Phase 0 — Skeleton.** Repo, env, DuckDB connection, one match flattened and queryable.
  Prove the data round-trips.
- **Phase 1 — End-to-end vertical slice (MVP, the ship gate).** La Liga 2015/16 only. ~6
  question archetypes. Full loop: plan → retrieve → SQL → verify → execute → synthesize →
  return. One viz type (shot map with xG). CLI to ask a question and get an answer.
- **Phase 2 — Web UI + trace.** Next.js chat, render answer + viz, "show the SQL" and
  expandable trace panel.
- **Phase 3 — Depth.** More viz templates (pass map, heatmap, pass network, progression map),
  the critic subagent, semantic + result caching, prompt-cache pre-warming, more marts.
- **Phase 4 — Breadth & rigor (in progress).** Full StatsBomb open-data catalog support:
  selective `etl add` per competition/season, scope resolution in the agent, tiered eval
  (`gold_core.jsonl` / `gold_breadth.jsonl`). Conversational context and observability
  dashboard remain future work.

## 9. Eval & quality

- **Gold set** (`eval/gold_core.jsonl`, optional `eval/gold_breadth.jsonl`): hand-verified
  questions per loaded competition scope. Core La Liga set is the ship gate.
- **Checks:** numbers in the answer match executed rows; entity resolution picks the right
  player/team; generated SQL passes the verifier; no invented stats.
- **Failure-driven exemplars:** every real failure that gets fixed becomes a new few-shot.

## 10. Guardrails for the coding agent

- **Ship Phase 1 before anything else.** A working vertical slice on one season beats a
  half-built comprehensive system. Resist scope creep.
- Don't build a vector DB service or embed event rows — retrieval is the three small corpora.
- Don't let synthesis produce any number not present in the executed result.
- Keep every query read-only, filtered, and capped.
- One repair loop, one critic bounce. No unbounded agent recursion.
- Prefer boring, verifiable SQL over clever pandas.
- Keep the trace complete — it's both the debugger and the showcase.
