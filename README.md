# PitchMind

> Ask football questions in plain English → get a data-grounded answer plus a pitch
> visualization. PitchMind plans the analysis, writes verifiable DuckDB SQL against
> flattened StatsBomb event data, runs it in a read-only sandbox, reasons over the
> **actual** result rows, and answers in football language.

PitchMind is a demonstration of **agentic LLM systems engineering** — a real tool-use
loop with planning, retrieval, SQL generation, static verification + dry-run, sandboxed
execution, and anti-hallucination synthesis — using football as a domain rich enough to
prove the system can reason over messy, real-world structured data.

It is also the reasoning layer beneath agentic scouting: natural-language briefs →
data-grounded shortlists. The querying that today needs an analyst who knows the schema,
in seconds.

## What it does (Phase 1)

```
pitchmind ask "which midfielders progressed the ball most under pressure in La Liga 2015/16?"
```

→ resolves the entities, generates DuckDB SQL, verifies and runs it read-only, and writes
a football-language answer (with a shot map where it helps). Add `--show-sql` or
`--show-trace` to see exactly how the answer was produced.

## How it works

```
question
   │
   ▼
 plan ─► resolve entities ─► retrieve (schema + glossary + few-shots, cached)
   │                                          │
   ▼                                          ▼
 generate SQL ─► verify (tables/cols real · filter · LIMIT · dry-run) ─┐
                                                                       │ one repair loop
   ┌───────────────────────────────────────────────────────────────────┘
   ▼
 execute (read-only · timeout · row cap) ─► viz (shot map) ─► synthesize (narrate over rows only)
   │
   ▼
 answer + viz + full trace
```

**Design principles**
- **DuckDB** for analytics (embedded, columnar, zero-ops), Postgres only for app state later.
- **Text-to-SQL, not text-to-pandas** — sandboxable, verifiable, and the model is excellent at it.
- **Narrow RAG** — only schema docs, a metric glossary, and few-shot exemplars are ever
  retrieved. Raw event rows live in DuckDB and get queried, never embedded.
- **Verification is first-class** — every query is statically checked and dry-run before it runs.
- **Numbers are computed, never generated** — synthesis only narrates over executed rows.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env      # add ANTHROPIC_API_KEY

# Build the data (Phase 1: La Liga 2015/16 only)
pitchmind etl download
pitchmind etl flatten
pitchmind etl load-duckdb
pitchmind etl entity-index
pitchmind etl marts

# Ask
pitchmind ask "who took the most shots for Barcelona in La Liga 2015/16?"
```

## Data & attribution

Data is **StatsBomb Open Data** (https://github.com/statsbomb/open-data), accessed via
`statsbombpy`. Use of StatsBomb open data requires attribution and acceptance of their
[user agreement](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf).

> **Data provided by StatsBomb.** PitchMind uses StatsBomb's free open data. StatsBomb is
> not affiliated with and does not endorse this project.

This attribution line is required and must remain in the README and any app footer.
