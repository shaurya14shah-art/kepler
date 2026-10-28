import { useEffect, useMemo, useRef, useState } from "react";
import { usePoll, useToast } from "../components/ui";
import { api, type Integration } from "../lib/api";
import { ago } from "../lib/format";

type Sel = { kind: "integration"; type: string } | { kind: "api" } | { kind: "csv" } | null;

const CATEGORY_LABEL: Record<string, string> = {
  observability: "Observability",
  "product analytics": "Product analytics",
  errors: "Errors",
  cloud: "Cloud",
  database: "Database",
  other: "Other",
};

function Initials({ label }: { label: string }) {
  const t = label.replace(/^AWS /, "").split(/\s+/).map((w) => w[0]).join("").slice(0, 2);
  return <span className="tile-logo" aria-hidden="true">{t}</span>;
}

function Tile({ title, sub, chip, active, onClick }: { title: string; sub: string; chip?: string; active: boolean; onClick: () => void }) {
  return (
    <button className={`tile ${active ? "active" : ""}`} onClick={onClick} aria-pressed={active}>
      <Initials label={title} />
      <span className="tile-text">
        <span className="tile-title">{title}</span>
        <span className="tile-sub">{sub}</span>
      </span>
      {chip && <span className="chip">{chip}</span>}
    </button>
  );
}

export function Connect() {
  const { data: catalog } = usePoll(api.integrations, 0);
  const connectors = usePoll(api.connectors, 15000);
  const destinations = usePoll(api.destinations, 15000);
  const [sel, setSel] = useState<Sel>(null);
  const panel = useRef<HTMLDivElement>(null);
  const choose = (s: Sel) => {
    setSel(s);
    requestAnimationFrame(() => panel.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const pull = (catalog ?? []).filter((i) => i.direction === "pull");
  const push = (catalog ?? []).filter((i) => i.direction === "push");
  const dests = (catalog ?? []).filter((i) => i.direction === "destination");
  const selected = sel?.kind === "integration" ? catalog?.find((i) => i.type === sel.type) : undefined;
  const isActive = (t: string) => sel?.kind === "integration" && sel.type === t;

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Integrations</h1>
          <p>Plug Kepler into the tools your team already uses: pull metrics from them, receive data pushed by them, and post incidents back into them.</p>
        </div>
      </div>

      <section className="stack">
        <h2>Pull metrics from</h2>
        <div className="tiles">
          {pull.map((i) => (
            <Tile key={i.type} title={i.label} sub={i.summary} chip={CATEGORY_LABEL[i.category]} active={isActive(i.type)}
              onClick={() => choose({ kind: "integration", type: i.type })} />
          ))}
        </div>
      </section>

      <section className="stack">
        <h2>Send data to Kepler</h2>
        <div className="tiles">
          <Tile title="Kepler API & SDK" sub="POST events or measurements from your code" chip="Any stack" active={sel?.kind === "api"} onClick={() => choose({ kind: "api" })} />
          {push.map((i) => (
            <Tile key={i.type} title={i.label} sub={i.summary} chip={CATEGORY_LABEL[i.category]} active={isActive(i.type)}
              onClick={() => choose({ kind: "integration", type: i.type })} />
          ))}
          <Tile title="CSV upload" sub="Import history to train custom models right away" chip="Files" active={sel?.kind === "csv"} onClick={() => choose({ kind: "csv" })} />
        </div>
      </section>

      <section className="stack">
        <h2>Send incidents to</h2>
        <div className="tiles">
          {dests.map((i) => (
            <Tile key={i.type} title={i.label} sub={i.summary} chip="Destination" active={isActive(i.type)}
              onClick={() => choose({ kind: "integration", type: i.type })} />
          ))}
          <Tile title="Slack" sub="Incoming webhook, configured in Settings" chip="Destination" active={false} onClick={() => (window.location.hash = "/settings")} />
        </div>
      </section>

      <div ref={panel} style={{ scrollMarginTop: 16 }}>
        {sel && (
          <div className="card pad stack">
            {sel.kind === "api" && <PushApiPanel />}
            {sel.kind === "csv" && <CsvPanel />}
            {selected?.direction === "pull" && <PullForm key={selected.type} integ={selected} onSaved={connectors.reload} />}
            {selected?.type === "segment" && <SegmentPanel integ={selected} />}
            {selected?.type === "otlp" && <OtlpPanel integ={selected} />}
            {selected?.direction === "destination" && <DestinationForm key={selected.type} integ={selected} onSaved={destinations.reload} />}
          </div>
        )}
      </div>

      {/* full width each: side by side, a five-column table got ~340 px and lost its Status and buttons */}
      <div className="stack">
        <div className="card table-wrap">
          <div className="card-head"><div><h2>Scheduled pulls</h2><p>Each runs every few minutes and fills its metric</p></div></div>
          <table>
            <thead><tr><th>Source</th><th>Metric</th><th>Last run</th><th>Status</th><th /></tr></thead>
            <tbody>
              {(connectors.data ?? []).map((c) => (
                <tr key={c.id}>
                  <td>{c.name}<div className="faint small">{c.label ?? c.type} · every {Math.round(c.interval_s / 60)} min</div></td>
                  <td className="mono">{c.config.metric}</td>
                  <td className="muted small">{c.last_run ? ago(c.last_run) : "never"}</td>
                  <td className="small" style={{ color: c.last_status.startsWith("error") ? "var(--critical)" : undefined }}>{c.last_status || "–"}</td>
                  <td className="row" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}>
                    <button className="btn sm" onClick={async () => { await api.runConnector(c.id); connectors.reload(); }}>Run</button>
                    <button className="btn sm danger" onClick={async () => { await api.deleteConnector(c.id); connectors.reload(); }}>Remove</button>
                  </td>
                </tr>
              ))}
              {connectors.data && !connectors.data.length && <tr><td colSpan={5} className="empty">No pulls yet. Pick a tool above.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="card table-wrap">
          <div className="card-head"><div><h2>Incident destinations</h2><p>Where Kepler posts incidents (besides Slack)</p></div></div>
          <table>
            <thead><tr><th>Destination</th><th>Sends</th><th>Status</th><th /></tr></thead>
            <tbody>
              {(destinations.data ?? []).map((d) => (
                <tr key={d.id}>
                  <td>{d.name}<div className="faint small">{d.label}</div></td>
                  <td className="small">{d.min_severity}+</td>
                  <td className="small" style={{ color: d.last_status.startsWith("error") ? "var(--critical)" : undefined }}>{d.last_status || "waiting for an incident"}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn sm danger" onClick={async () => { await api.deleteDestination(d.id); destinations.reload(); }}>Remove</button>
                  </td>
                </tr>
              ))}
              {destinations.data && !destinations.data.length && <tr><td colSpan={4} className="empty">No destinations yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- dynamic forms

function useFieldState(integ: Integration) {
  const initial = useMemo(() => Object.fromEntries(integ.fields.map((f) => [f.name, f.default])), [integ]);
  const [values, setValues] = useState<Record<string, string>>(initial);
  useEffect(() => setValues(initial), [initial]);
  return [values, setValues] as const;
}

function Fields({ integ, values, set }: { integ: Integration; values: Record<string, string>; set: (k: string, v: string) => void }) {
  const wide = (k: string) => k === "textarea";
  return (
    <div className="form-grid">
      {integ.fields.map((f) => (
        <label key={f.name} className="field" style={wide(f.kind) ? { gridColumn: "1 / -1" } : undefined}>
          <span>{f.label}{!f.required && <span className="hint"> (optional)</span>}</span>
          {f.kind === "select" ? (
            <select value={values[f.name]} onChange={(e) => set(f.name, e.target.value)}>
              {f.options.map((o) => <option key={o}>{o}</option>)}
            </select>
          ) : f.kind === "textarea" ? (
            <textarea value={values[f.name]} onChange={(e) => set(f.name, e.target.value)} rows={4} spellCheck={false} />
          ) : (
            <input type={f.kind === "password" ? "password" : f.kind === "url" ? "url" : f.kind === "number" ? "text" : "text"}
              inputMode={f.kind === "number" ? "numeric" : undefined} autoComplete="off"
              value={values[f.name]} onChange={(e) => set(f.name, e.target.value)} />
          )}
          {f.help && <span className="hint">{f.help}</span>}
        </label>
      ))}
    </div>
  );
}

function PanelHead({ integ }: { integ: Integration }) {
  return (
    <div className="row" style={{ alignItems: "flex-start" }}>
      <Initials label={integ.label} />
      <div style={{ flex: 1 }}>
        <h2>{integ.label}</h2>
        <p className="muted small">{integ.summary}</p>
      </div>
      {integ.docs && <a className="small" href={integ.docs} target="_blank" rel="noreferrer">API docs ↗</a>}
    </div>
  );
}

function PullForm({ integ, onSaved }: { integ: Integration; onSaved: () => void }) {
  const [values, setValues] = useFieldState(integ);
  const [meta, setMeta] = useState({ name: "", agg: integ.default_agg, bad: integ.default_bad, every: "5" });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const toast = useToast();
  const set = (k: string, v: string) => setValues({ ...values, [k]: v });
  const body = () => ({
    type: integ.type,
    name: meta.name || `${integ.label}: ${values.metric || "metric"}`,
    interval_s: Math.max(1, Number(meta.every)) * 60,
    config: { ...values, agg: meta.agg, bad_direction: meta.bad },
  });
  const test = async () => {
    setMsg({ ok: true, text: "Querying…" });
    const r = await api.testConnector(body());
    setMsg({ ok: r.ok, text: r.message + (r.segments?.length ? ` · segments: ${r.segments.slice(0, 4).join(", ")}` : "") });
  };
  const save = async () => {
    try {
      await api.createConnector(body());
      toast(`${integ.label} connected. First pull runs within a minute.`);
      setMsg({ ok: true, text: "Saved." });
      onSaved();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };
  return (
    <>
      <PanelHead integ={integ} />
      <Fields integ={integ} values={values} set={set} />
      <div className="form-grid">
        <label className="field">Connection name<input type="text" value={meta.name} placeholder={`${integ.label}: ${values.metric || "metric"}`} onChange={(e) => setMeta({ ...meta, name: e.target.value })} /></label>
        <label className="field">Aggregation
          <select value={meta.agg} onChange={(e) => setMeta({ ...meta, agg: e.target.value as "sum" | "mean" })}>
            <option value="sum">sum (counts)</option><option value="mean">mean (measurements)</option>
          </select>
        </label>
        <label className="field">Alert when it goes
          <select value={meta.bad} onChange={(e) => setMeta({ ...meta, bad: e.target.value as "up" | "down" | "both" })}>
            <option value="up">up</option><option value="down">down</option><option value="both">either way</option>
          </select>
        </label>
        <label className="field">Pull every (minutes)<input type="text" inputMode="numeric" value={meta.every} onChange={(e) => setMeta({ ...meta, every: e.target.value })} /></label>
      </div>
      <div className="row">
        <button className="btn" onClick={test}>Test connection</button>
        <button className="btn primary" onClick={save}>Save & start pulling</button>
      </div>
      {msg && <div className={`notice ${msg.ok ? "ok" : "err"}`}>{msg.text}</div>}
    </>
  );
}

function DestinationForm({ integ, onSaved }: { integ: Integration; onSaved: () => void }) {
  const [values, setValues] = useFieldState(integ);
  const [name, setName] = useState(integ.label);
  const [minSev, setMinSev] = useState("high");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const set = (k: string, v: string) => setValues({ ...values, [k]: v });
  const body = () => ({ type: integ.type, name, config: values, min_severity: minSev });
  return (
    <>
      <PanelHead integ={integ} />
      <Fields integ={integ} values={values} set={set} />
      <div className="form-grid">
        <label className="field">Name<input type="text" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="field">Send incidents of severity
          <select value={minSev} onChange={(e) => setMinSev(e.target.value)}>
            <option value="medium">medium and above</option><option value="high">high and above</option><option value="critical">critical only</option>
          </select>
        </label>
      </div>
      <div className="row">
        <button className="btn" onClick={async () => { setMsg({ ok: true, text: "Sending…" }); const r = await api.testDestination(body()); setMsg({ ok: r.ok, text: r.message }); }}>Send test event</button>
        <button className="btn primary" onClick={async () => {
          try { await api.createDestination(body()); setMsg({ ok: true, text: "Saved. New incidents will be posted here." }); onSaved(); }
          catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
        }}>Save destination</button>
      </div>
      {msg && <div className={`notice ${msg.ok ? "ok" : "err"}`}>{msg.text}</div>}
    </>
  );
}

// ---------------------------------------------------------------- push panels

function useKey() {
  const { data } = usePoll(api.settings, 0);
  return data?.api_key ?? "kp_…";
}

function PushApiPanel() {
  const key = useKey();
  const host = window.location.origin;
  return (
    <>
      <h2>Kepler API & SDK</h2>
      <p className="muted">Send events or measurements from your code. Kepler groups them into 5-minute windows and scores each window once it's complete.</p>
      <pre className="code">{`curl -X POST ${host}/api/v1/ingest \\
  -H "X-Kepler-Key: ${key}" -H "Content-Type: application/json" \\
  -d '{"metrics": [{"name": "signups", "value": 1, "dims": {"platform": "ios"}},
                   {"name": "p95_latency_ms", "value": 182.5, "agg": "mean"}]}'`}</pre>
      <pre className="code">{`# Python: copy backend/sdk/kepler_client.py into your project
from kepler_client import Kepler
kepler = Kepler("${host}", "${key}")
kepler.track("signups", platform="ios")       # counts
kepler.gauge("p95_latency_ms", 182.5)         # measurements
kepler.flush()`}</pre>
      <pre className="code">{`# CLI
kepler send signups 1 --dim platform=ios`}</pre>
    </>
  );
}

function SegmentPanel({ integ }: { integ: Integration }) {
  const key = useKey();
  const [dims, setDims] = useState(integ.fields[0]?.default ?? "");
  const url = `${window.location.origin}/api/v1/hooks/segment?key=${key}${dims ? `&dims=${encodeURIComponent(dims)}` : ""}`;
  return (
    <>
      <PanelHead integ={integ} />
      <ol className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
        <li>In Segment, go to <b>Connections → Destinations → Add destination → Webhooks (Actions)</b>.</li>
        <li>Add a <b>Send</b> mapping for Track and Page events, method POST, with the URL below.</li>
        <li>Each event becomes a metric: <code>Signed Up</code> → <code>signed_up</code>, pages → <code>page_views</code>.</li>
      </ol>
      <label className="field">Properties to keep as dimensions (comma-separated; dotted paths allowed)
        <input type="text" value={dims} onChange={(e) => setDims(e.target.value)} />
      </label>
      <pre className="code">{url}</pre>
      <p className="faint small">Kepler must be reachable from the internet for Segment to call it (deploy it, or use a tunnel while testing).</p>
    </>
  );
}

function OtlpPanel({ integ }: { integ: Integration }) {
  const key = useKey();
  const host = window.location.origin;
  return (
    <>
      <PanelHead integ={integ} />
      <p className="muted small">Add Kepler as an extra exporter in your OpenTelemetry Collector. It accepts OTLP/HTTP with JSON encoding.</p>
      <pre className="code">{`exporters:
  otlphttp/kepler:
    endpoint: ${host}
    encoding: json
    headers:
      X-Kepler-Key: ${key}

service:
  pipelines:
    metrics:
      exporters: [otlphttp/kepler]   # alongside your existing exporters`}</pre>
      <p className="muted small">Or straight from an SDK: <code>OTEL_EXPORTER_OTLP_METRICS_ENDPOINT={host}/v1/metrics</code>, <code>OTEL_EXPORTER_OTLP_METRICS_PROTOCOL=http/json</code>, <code>OTEL_EXPORTER_OTLP_HEADERS=X-Kepler-Key={key}</code>.</p>
    </>
  );
}

function CsvPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [metric, setMetric] = useState("");
  const [agg, setAgg] = useState("sum");
  const [bad, setBad] = useState("both");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const upload = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("metric", metric);
    form.append("agg", agg);
    form.append("bad_direction", bad);
    try {
      const r = await api.importCsv(form);
      setMsg({ ok: true, text: `Imported ${r.rows} rows into ${Object.keys(r.metrics).join(", ")}${r.dimensions.length ? ` (dimensions: ${r.dimensions.join(", ")})` : ""}. Retrain models on the Models page to learn from it.` });
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };
  return (
    <>
      <h2>CSV upload</h2>
      <p className="muted small">Long format: <code>timestamp,metric,value</code> plus any extra columns as dimensions. Try <code>kepler analyze file.csv</code> to score a CSV from the terminal without importing it.</p>
      <div className="form-grid">
        <label className="field">CSV file<input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
        <label className="field">Metric name <span className="hint">if the CSV has no metric column</span><input type="text" value={metric} onChange={(e) => setMetric(e.target.value)} /></label>
        <label className="field">Aggregation<select value={agg} onChange={(e) => setAgg(e.target.value)}><option value="sum">sum</option><option value="mean">mean</option></select></label>
        <label className="field">Alert when it goes<select value={bad} onChange={(e) => setBad(e.target.value)}><option value="both">either way</option><option value="up">up</option><option value="down">down</option></select></label>
      </div>
      <div><button className="btn primary" disabled={!file} onClick={upload}>Import CSV</button></div>
      {msg && <div className={`notice ${msg.ok ? "ok" : "err"}`}>{msg.text}</div>}
    </>
  );
}
