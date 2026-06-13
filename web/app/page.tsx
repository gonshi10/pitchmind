"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const EXAMPLES = [
  "Which players progressed the ball most under pressure in La Liga 2015/16?",
  "Who scored the most goals in La Liga 2015/16?",
  "Show me Lionel Messi's shot map for La Liga 2015/16",
  "Who took the most shots for Barcelona in La Liga 2015/16?",
  "Which team generated the most expected goals in La Liga 2015/16?",
  "How many goals did Cristiano Ronaldo score in La Liga 2015/16?",
];

type Entity = {
  text: string;
  kind: string;
  entity_id: number | null;
  resolved_name: string | null;
  confidence: number | null;
  note: string | null;
};

type Run = {
  question: string;
  reached: Set<string>;
  plan?: { question_type: string; metric: string; wants_viz: boolean; viz_type: string | null };
  entities?: Entity[];
  sql?: string;
  attempt?: number;
  repairs: number;
  verifyOk?: boolean;
  errors?: string[];
  execute?: { columns: string[]; row_count: number; rows_preview: any[] };
  vizFilename?: string;
  answer?: string;
  runId?: string;
  elapsed?: number | null;
  rows?: any[];
  vizUrl?: string | null;
  error?: { where?: string; message: string };
};

const STAGE_DEFS = [
  { key: "plan", label: "Plan" },
  { key: "entities", label: "Resolve entities" },
  { key: "sql_generated", label: "Generate SQL" },
  { key: "verify", label: "Verify" },
  { key: "execute", label: "Execute" },
  { key: "viz", label: "Render shot map" },
  { key: "synthesis", label: "Write answer" },
];

type Status = "idle" | "streaming" | "done" | "error";

export default function Page() {
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [run, setRun] = useState<Run | null>(null);
  const [health, setHealth] = useState<"unknown" | "up" | "down">("unknown");
  const esRef = useRef<EventSource | null>(null);
  const statusRef = useRef<Status>("idle");
  statusRef.current = status;

  const autoRan = useRef(false);

  useEffect(() => {
    fetch(`${API}/health`)
      .then((r) => r.json())
      .then((d) => setHealth(d.db_present ? "up" : "down"))
      .catch(() => setHealth("down"));

    // Deep link: /?q=... auto-runs the question (shareable links).
    const q = new URLSearchParams(window.location.search).get("q");
    if (q && !autoRan.current) {
      autoRan.current = true;
      setInput(q);
      ask(q);
    }
    return () => esRef.current?.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function patch(p: Partial<Run>, reachedKey?: string) {
    setRun((prev) => {
      const base: Run = prev ?? { question: "", reached: new Set(), repairs: 0 };
      const reached = new Set(base.reached);
      if (reachedKey) reached.add(reachedKey);
      return { ...base, ...p, reached };
    });
  }

  function ask(q: string) {
    const question = q.trim();
    if (!question || status === "streaming") return;
    esRef.current?.close();
    setRun({ question, reached: new Set(), repairs: 0 });
    setStatus("streaming");

    const es = new EventSource(
      `${API}/ask/stream?question=${encodeURIComponent(question)}`
    );
    esRef.current = es;

    const on = (name: string, fn: (d: any) => void) =>
      es.addEventListener(name, (e) => fn(JSON.parse((e as MessageEvent).data)));

    on("plan", (d) => patch({ plan: d }, "plan"));
    on("entities", (d) => patch({ entities: d.entities }, "entities"));
    on("sql_generated", (d) => patch({ sql: d.sql, attempt: d.attempt }, "sql_generated"));
    on("verify", (d) => patch({ verifyOk: d.ok, errors: d.errors }, "verify"));
    on("repair", () => setRun((p) => (p ? { ...p, repairs: p.repairs + 1 } : p)));
    on("execute", (d) => patch({ execute: d }, "execute"));
    on("viz", (d) => patch({ vizFilename: d.filename }, "viz"));
    on("synthesis", (d) => patch({ answer: d.answer }, "synthesis"));
    on("result", (d) => {
      patch({
        answer: d.answer,
        sql: d.sql,
        rows: d.rows,
        runId: d.run_id,
        elapsed: d.elapsed_s,
        vizUrl: d.viz_url,
      });
    });
    on("agent_error", (d) => {
      patch({ error: { message: d.message } });
      setStatus("error");
      es.close();
    });
    es.addEventListener("done", () => {
      setStatus((s) => (s === "error" ? s : "done"));
      es.close();
    });
    es.onerror = () => {
      if (statusRef.current === "streaming") {
        patch({ error: { message: "Lost the connection to the agent service." } });
        setStatus("error");
      }
      es.close();
    };
  }

  const showViz = !!run?.vizFilename || run?.plan?.viz_type === "shot_map";
  const stages = STAGE_DEFS.filter((s) => s.key !== "viz" || showViz);
  const maxReached = stages.reduce(
    (m, s, i) => (run?.reached.has(s.key) ? i : m),
    -1
  );

  function stageState(i: number, key: string): "pending" | "active" | "done" | "failed" {
    if (run?.error?.where === "verify" && key === "verify") return "failed";
    if (run?.error?.where === "execute" && key === "execute") return "failed";
    if (status === "done" || status === "error") return i <= maxReached ? "done" : "pending";
    if (i <= maxReached) return "done";
    if (i === maxReached + 1) return "active";
    return "pending";
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="wordmark">
          <span className="dot" />
          PITCHMIND
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span className="pill">La Liga 2015/16</span>
          <span className={`status ${health === "up" ? "live" : health === "down" ? "down" : ""}`}>
            <span className="led" />
            {health === "up" ? "engine online" : health === "down" ? "engine offline" : "checking"}
          </span>
        </div>
      </header>

      {!run && (
        <section className="hero">
          <div className="eyebrow">Natural-language football analytics</div>
          <h1>
            Ask the data.
            <br />
            Get a <span className="accent">scout's</span> answer.
          </h1>
          <p className="lede">
            PitchMind plans the analysis, writes verifiable SQL over StatsBomb event data, runs
            it read-only, and reasons over the actual rows — never an invented number.
          </p>
        </section>
      )}

      <Command
        input={input}
        setInput={setInput}
        onSubmit={() => ask(input)}
        streaming={status === "streaming"}
        compact={!!run}
      />

      {!run && (
        <div className="chips">
          {EXAMPLES.map((q) => (
            <button
              key={q}
              className="chip"
              onClick={() => {
                setInput(q);
                ask(q);
              }}
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {run && (
        <>
          <div className="echo">
            <span className="q-mark">▸</span>
            <span className="q-text">{run.question}</span>
          </div>

          <div className="pipeline">
            {stages.map((s, i) => {
              const st = stageState(i, s.key);
              return (
                <div key={s.key} className={`stage ${st}`}>
                  <span className="node" />
                  <div className="label">{s.label}</div>
                  <div className="detail">{stageDetail(s.key, run, st)}</div>
                </div>
              );
            })}
          </div>

          {run.error && <div className="error">{run.error.message}</div>}

          {run.answer && status !== "error" && (
            <div className="result">
              <div className="answer">
                <ReactMarkdown>{run.answer}</ReactMarkdown>
              </div>

              {run.vizUrl && (
                <div className="viz">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`${API}${run.vizUrl}`} alt="Shot map" />
                  <div className="cap">SHOT MAP · MARKER SIZE ∝ xG · RED = GOAL</div>
                </div>
              )}

              <div className="disclosures">
                {run.sql && (
                  <details className="disc">
                    <summary>
                      <span>Show the SQL</span>
                      <span className="chev">›</span>
                    </summary>
                    <div className="disc-body">
                      <pre className="sql">{run.sql}</pre>
                    </div>
                  </details>
                )}

                <details className="disc">
                  <summary>
                    <span>How I got this</span>
                    <span className="chev">›</span>
                  </summary>
                  <div className="disc-body">
                    <TracePanel run={run} />
                  </div>
                </details>
              </div>
            </div>
          )}
        </>
      )}

      <footer className="foot">
        <b>Data provided by StatsBomb.</b> PitchMind uses StatsBomb's free open data. StatsBomb
        is not affiliated with and does not endorse this project.
        <br />
        Every answer is computed from verified, read-only SQL over the event data — numbers are
        never generated by the model.
      </footer>
    </div>
  );
}

function Command({
  input,
  setInput,
  onSubmit,
  streaming,
  compact,
}: {
  input: string;
  setInput: (v: string) => void;
  onSubmit: () => void;
  streaming: boolean;
  compact: boolean;
}) {
  return (
    <div className="command" style={compact ? { marginTop: 24 } : undefined}>
      <span className="prompt">⌕</span>
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onSubmit()}
        placeholder="Which midfielder progressed the ball most under pressure?"
        autoFocus
      />
      <button onClick={onSubmit} disabled={streaming || !input.trim()}>
        {streaming ? "Analyzing…" : "Analyze"}
      </button>
    </div>
  );
}

function stageDetail(key: string, run: Run, st: string) {
  if (st === "pending") return "";
  switch (key) {
    case "plan":
      return run.plan ? (
        <>
          <span className="tag">{run.plan.question_type}</span>
          {run.plan.metric}
        </>
      ) : (
        "classifying the question…"
      );
    case "entities":
      if (!run.entities) return "resolving names…";
      if (run.entities.length === 0) return "no specific player or team";
      return run.entities.map((e, i) => (
        <span className="ent" key={i}>
          {e.text} → <b>{e.resolved_name ?? "?"}</b>
          {e.confidence != null ? ` (${Math.round(e.confidence)})` : ""}
        </span>
      ));
    case "sql_generated":
      return (
        <>
          drafted DuckDB SQL
          {run.repairs > 0 && <span className="tag warn">repaired ×{run.repairs}</span>}
        </>
      );
    case "verify":
      if (run.verifyOk === undefined) return "checking tables, filters, LIMIT…";
      return run.verifyOk ? (
        <span className="tag">passed all checks + dry-run</span>
      ) : (
        <span className="tag warn">{(run.errors ?? []).join("; ")}</span>
      );
    case "execute":
      return run.execute ? (
        <>
          <span className="tag">{run.execute.row_count} rows</span>
          {run.execute.columns.length} columns, read-only
        </>
      ) : (
        "running on the sandbox…"
      );
    case "viz":
      return run.vizFilename ? <span className="tag">shot map rendered</span> : "rendering…";
    case "synthesis":
      return run.answer ? (
        <span className="tag">{run.elapsed != null ? `${run.elapsed}s total` : "answer ready"}</span>
      ) : (
        "writing the answer over the rows…"
      );
    default:
      return "";
  }
}

function TracePanel({ run }: { run: Run }) {
  const rows = run.rows ?? run.execute?.rows_preview ?? [];
  const cols = run.execute?.columns ?? (rows[0] ? Object.keys(rows[0]) : []);
  return (
    <div className="trace-grid">
      {run.plan && (
        <div className="trace-block">
          <div className="t-head">Plan</div>
          <div className="kv">
            type <b>{run.plan.question_type}</b> · metric <b>{run.plan.metric}</b> · viz{" "}
            <b>{run.plan.viz_type ?? "none"}</b>
          </div>
        </div>
      )}

      {run.entities && run.entities.length > 0 && (
        <div className="trace-block">
          <div className="t-head">Resolved entities</div>
          <div>
            {run.entities.map((e, i) => (
              <span className="ent" key={i}>
                {e.kind}:{e.text} → <b>{e.resolved_name ?? "unresolved"}</b>
                {e.entity_id != null ? ` #${e.entity_id}` : ""}
                {e.confidence != null ? ` (${Math.round(e.confidence)})` : ""}
              </span>
            ))}
          </div>
        </div>
      )}

      {rows.length > 0 && (
        <div className="trace-block">
          <div className="t-head">Result rows ({run.execute?.row_count ?? rows.length})</div>
          <div className="rows-wrap">
            <table className="rows">
              <thead>
                <tr>
                  {cols.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 12).map((r, i) => (
                  <tr key={i}>
                    {cols.map((c) => (
                      <td key={c}>{formatCell(r[c])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="trace-block">
        <div className="t-head">Run</div>
        <div className="kv">
          id <b>{run.runId ?? "—"}</b>
          {run.elapsed != null ? (
            <>
              {" "}
              · <b>{run.elapsed}s</b>
            </>
          ) : null}
          {run.repairs > 0 ? <> · repairs <b>{run.repairs}</b></> : null}
        </div>
      </div>
    </div>
  );
}

function formatCell(v: any) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? v : v.toFixed(2);
  return String(v);
}
