---
description: Start the PitchMind backend (and optionally the web app) and report URLs
allowed-tools: Bash(pitchmind serve:*), Bash(uvicorn:*), Bash(npm:*)
---

Start the PitchMind services for a local demo and report the URLs.

1. Backend (FastAPI): `pitchmind serve` (defaults to http://127.0.0.1:8000). Confirm
   `GET /health` returns `db_present: true` — if not, the ETL hasn't been run (`/etl`).
2. Frontend (Next.js): from `web/`, `npm install` (first run) then `npm run dev`
   (http://localhost:3000). It talks to the backend via `NEXT_PUBLIC_API_URL`.

Report both URLs. Note that `pitchmind ask`/the web app need `ANTHROPIC_API_KEY` in `.env`
or `.env.local`. Prefer running each service in the background so the shell stays free.
