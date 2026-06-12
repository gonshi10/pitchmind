---
description: Ask PitchMind a question and show the full trace
argument-hint: <football question>
allowed-tools: Bash(pitchmind:*), Bash(python -m pitchmind.cli:*)
---

Run `pitchmind ask --show-trace "$ARGUMENTS"` and review the result against the guardrails:

- Is the generated SQL **read-only**, **filtered** (competition + season), and **`LIMIT`-capped**?
- Did entity resolution pick the right player/team?
- **Does every number in the answer appear in the executed result rows?** (No invented stats.)
- If a viz was produced, is the PNG path reported and does the chart match the rows?

Summarize the answer, then flag any guardrail the run violated. If the SQL was wrong in a way
worth remembering, suggest a new exemplar for `knowledge/exemplars.jsonl` (see `/new-exemplar`).
