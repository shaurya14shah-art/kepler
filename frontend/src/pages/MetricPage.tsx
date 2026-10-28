import { useState } from "react";
import { MetricChart } from "../components/Charts";
import { ComparePanel, TierBadge } from "../components/Tiers";
import { useOpenIncident } from "../components/IncidentDrawer";
import { SevChip, StatusChip, WhereChips, go, usePoll, useToast } from "../components/ui";
import { api } from "../lib/api";
import { changeText, dateTime, duration, num, pct } from "../lib/format";

const RANGES = [
  { h: 6, label: "6 h" },
  { h: 24, label: "24 h" },
  { h: 72, label: "3 d" },
  { h: 168, label: "7 d" },
];

const MUTES = [
  { label: "1 h", s: 3600 },
  { label: "4 h", s: 4 * 3600 },
  { label: "24 h", s: 86400 },
];

/** Pause this metric's alerts for a while (deploys, maintenance). Incidents are still detected and recorded. */
function MuteControl({ id, mutedUntil, onChange }: { id: number; mutedUntil: number; onChange: () => void }) {
  const [open, setOpen] = useState(false);
  const toast = useToast();
  const muted = mutedUntil > Date.now() / 1000;
  async function set(until: number) {
    await api.patchMetric(id, { muted_until: until });
    setOpen(false);
    onChange();
    toast(until ? `Alerts muted until ${dateTime(until)}` : "Alerts are on again");
  }
  if (muted) {
    return (
      <span className="row" style={{ gap: 4 }}>
        <span className="chip" title="Incidents are still detected and recorded; no alerts go out">🔕 muted until {dateTime(mutedUntil)}</span>
        <button className="btn sm" onClick={() => set(0)}>Unmute</button>
      </span>
    );
  }
  return open ? (
    <span className="row" style={{ gap: 4 }}>
      <span className="small muted">Mute alerts for</span>
      {MUTES.map((x) => (
        <button key={x.s} className="btn sm" onClick={() => set(Math.floor(Date.now() / 1000) + x.s)}>{x.label}</button>
      ))}
      <button className="btn sm" onClick={() => setOpen(false)}>Cancel</button>
    </span>
  ) : (
    <button className="btn sm" title="Pause alerts for a while; detection goes on" onClick={() => setOpen(true)}>🔕 Mute</button>
  );
}

export function MetricPage({ id }: { id: number }) {
  const [hours, setHours] = useState(24);
  const [slice, setSlice] = useState("");
  const [editing, setEditing] = useState(false);
  const open = useOpenIncident();
  const toast = useToast();
  const { data, error, reload } = usePoll(() => api.series(id, hours, slice), 15000, [id, hours, slice]);
  const breakdown = usePoll(() => api.breakdown(id), 30000, [id]);

  if (error) return <div className="notice err">{error}</div>;
  if (!data) return <div className="muted">Loading…</div>;
  const m = data.metric;
  const last = [...data.points].reverse().find((p) => p.value !== null);
  const openInc = data.incidents.filter((d) => d.status === "open");

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <a href="#/" className="small">← Overview</a>
          <h1 className="mono" style={{ marginTop: 4 }}>{m.name}</h1>
          <p>
            {m.description || "No description"} · {m.agg === "mean" ? "averaged" : "summed"} per 5 min · alerts when it goes{" "}
            {m.bad_direction === "both" ? "up or down" : m.bad_direction} · source: {m.source}
            {(data.reports_every_s ?? 300) > 300 && (
              <span title="Kepler works in 5-minute buckets; this metric changes less often, so its evidence is counted per reading">
                {" "}· reports every {Math.round((data.reports_every_s ?? 300) / 60)} min
              </span>
            )}
          </p>
        </div>
        <div className="row">
          <StatusChip status={openInc.length ? "anomaly" : "ok"} />
          <TierBadge tier={data.tier} />
          <MuteControl id={id} mutedUntil={Number(m.muted_until) || 0} onChange={reload} />
          <span className="chip accent" title={data.model}>{data.model_kind === "custom" ? "custom baseline" : "shared baseline"}</span>
          <button className="btn sm" onClick={() => setEditing(!editing)}>Settings</button>
        </div>
      </div>

      {editing && <MetricSettings id={id} metric={m} onSaved={() => { setEditing(false); reload(); toast("Metric updated"); }} />}

      <div className="card pad">
        <div className="row" style={{ marginBottom: 12 }}>
          <div>
            <div className="muted small">Latest {slice && <span className="mono">({slice})</span>}</div>
            <div style={{ fontSize: 26, fontWeight: 700 }}>
              {num(last?.value)} <span className="muted" style={{ fontSize: 14, fontWeight: 500 }}>{m.unit}</span>
            </div>
            <div className="muted small">expected {num(last?.expected)} · normal range {num(last?.lower)}–{num(last?.upper)}</div>
          </div>
          <span className="spacer" />
          <div className="row" style={{ gap: 4 }}>
            {RANGES.map((r) => (
              <button key={r.h} className={`btn sm ${hours === r.h ? "on" : ""}`} onClick={() => setHours(r.h)}>{r.label}</button>
            ))}
          </div>
        </div>
        <div className="row" style={{ gap: 6, marginBottom: 12 }}>
          <span className="small muted">Slice:</span>
          <button className={`btn sm ${slice === "" ? "on" : ""}`} onClick={() => setSlice("")}>all</button>
          {data.slices.map((s) => (
            <button key={s} className={`btn sm mono ${slice === s ? "on" : ""}`} onClick={() => setSlice(s)}>{s}</button>
          ))}
        </div>
        <MetricChart points={data.points} incidents={data.incidents} unit={m.unit} height={320} />
        <p className="faint small" style={{ marginTop: 6 }}>
          Solid = actual · dashed = what Kepler expected · shaded band = normal range · red areas = incidents. Model: {data.model}.
        </p>
      </div>

      <ComparePanel metricId={id} current={data.tier} onSetTier={reload} />

      <div className="grid two">
        <div className="card">
          <div className="card-head">
            <div>
              <h2>Slices right now</h2>
              <p>Each slice against its own expectation, for the last completed 5 min</p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Slice</th><th>Now</th><th>Expected</th><th>Change</th><th>z</th></tr>
              </thead>
              <tbody>
                {(breakdown.data?.slices ?? []).map((s) => {
                  const hot = s.z !== null && Math.abs(s.z) >= 3;
                  return (
                    <tr key={s.slice} className="clickable" onClick={() => setSlice(s.slice)}>
                      <td className="mono">{s.slice}</td>
                      <td>{num(s.observed)}</td>
                      <td className="muted">{num(s.expected)}</td>
                      <td style={{ color: hot ? "var(--critical)" : undefined, fontWeight: hot ? 700 : undefined }}>{pct(s.change_pct)}</td>
                      <td className="muted">{s.z?.toFixed(1) ?? "–"}</td>
                    </tr>
                  );
                })}
                {breakdown.data && !breakdown.data.slices.length && (
                  <tr><td colSpan={5} className="empty">This metric has no dimensions. Send dims (e.g. platform, region) to get drilldowns.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <h2>Incidents in range</h2>
              <p>{data.incidents.length} for {slice || "the whole metric"}</p>
            </div>
          </div>
          {data.incidents.length === 0 && <div className="empty">Nothing unusual in this window 🎉</div>}
          {[...data.incidents].reverse().map((d) => (
            <div key={d.incident_id} className="incident-row" onClick={() => open(d.incident_id)} role="button" tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && open(d.incident_id)}>
              <div className={`sev-bar ${d.severity}`} />
              <div>
                <div className="title">{changeText(d)} <span className="muted small">· {dateTime(d.started_at)} · {duration(d.started_at, d.last_seen_at)}</span></div>
                <div style={{ marginTop: 4 }}><WhereChips where={d.where} /></div>
              </div>
              <div className="row">
                <SevChip severity={d.severity} />
                {d.feedback === 1 && <span title="labelled real">👍</span>}
                {d.feedback === 0 && <span title="labelled false alarm">👎</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MetricSettings({ id, metric, onSaved }: { id: number; metric: { unit: string; description: string; bad_direction: string; agg: string }; onSaved: () => void }) {
  const [f, setF] = useState({ unit: metric.unit, description: metric.description, bad_direction: metric.bad_direction, agg: metric.agg });
  const toast = useToast();
  const save = async () => {
    try {
      await api.patchMetric(id, f as never);
      onSaved();
    } catch (e) {
      toast((e as Error).message);
    }
  };
  const remove = async () => {
    if (!confirm("Delete this metric and all of its data? This cannot be undone.")) return;
    await api.deleteMetric(id);
    go("/");
  };
  return (
    <div className="card pad stack">
      <div className="form-grid">
        <label className="field">Description<input type="text" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
        <label className="field">Unit<input type="text" value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} /></label>
        <label className="field">Alert when it goes
          <select value={f.bad_direction} onChange={(e) => setF({ ...f, bad_direction: e.target.value })}>
            <option value="up">up (errors, latency)</option>
            <option value="down">down (signups, traffic)</option>
            <option value="both">either way</option>
          </select>
        </label>
        <label className="field">Aggregation
          <select value={f.agg} onChange={(e) => setF({ ...f, agg: e.target.value })}>
            <option value="sum">sum (counts)</option>
            <option value="mean">mean (measurements)</option>
          </select>
        </label>
      </div>
      <div className="row">
        <button className="btn primary" onClick={save}>Save</button>
        <span className="spacer" />
        <button className="btn danger" onClick={remove}>Delete metric</button>
      </div>
    </div>
  );
}
