# PitchMind

> Ask football questions in plain English → get a data-grounded answer plus a pitch
> visualization. PitchMind plans the analysis, writes verifiable DuckDB SQL against
> flattened StatsBomb event data, runs it in a read-only sandbox, reasons over the
> **actual** result rows, and answers in football language.

PitchMind is a demonstration of **agentic LLM systems engineering** — a real tool-use
loop with planning, retrieval, SQL generation, static verification + dry-run, sandboxed
execution, and anti-hallucination synthesis — using football as a domain rich enough to
prove the system can reason over messy, real-world structured data.

## What it does

```
pitchmind ask "which midfielders progressed the ball most under pressure in La Liga 2015/16?"
```

→ resolves competition/season scope, entities, generates DuckDB SQL, verifies and runs it
read-only, and writes a football-language answer (with a shot map where it helps). Add
`--show-sql` or `--show-trace` to see exactly how the answer was produced.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env      # add ANTHROPIC_API_KEY

# Sync the StatsBomb open-data catalog, then ingest what you need
pitchmind etl catalog
pitchmind etl add --name "La Liga 2015/16"

# Or ingest everything (hours; large disk)
# pitchmind etl all --everything

# Ask
pitchmind ask "who took the most shots for Barcelona in La Liga 2015/16?"
```

### ETL commands

| Command | Purpose |
|---------|---------|
| `pitchmind etl catalog` | Sync full `sb.competitions()` catalog |
| `pitchmind etl list` | Show catalog vs locally loaded targets |
| `pitchmind etl add --name "World Cup 2018"` | Ingest one competition/season |
| `pitchmind etl add --competition-id 43 --season-id 3` | Ingest by StatsBomb ids |
| `pitchmind etl all` | Rebuild DuckDB/views/marts from parquet (no network) |
| `pitchmind etl all --everything` | Bulk ingest every catalog target |

A full corpus may use **5–15 GB** parquet and take **multiple hours** on first download.

## Data & attribution

Data is **StatsBomb Open Data** (https://github.com/statsbomb/open-data), accessed via
`statsbombpy`. Use of StatsBomb open data requires attribution and acceptance of their
[user agreement](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf).

> **Data provided by StatsBomb.** PitchMind uses StatsBomb's free open data. StatsBomb is
> not affiliated with and does not endorse this project.

This attribution line is required and must remain in the README and any app footer.
