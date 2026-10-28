import { useEffect, useState } from "react";
import { Sparkline } from "../components/Charts";
import { useOpenIncident } from "../components/IncidentDrawer";
import { SevChip, StatusChip, WhereChips, go, useToast } from "../components/ui";
import { api, type Decision, type Overview as OverviewT } from "../lib/api";
import { ago, changeText, dateTime, num, pct } from "../lib/format";

export function Overview({ data, reload, demo }: { data: OverviewT | null; reload: () => void; demo: boolean }) {
  const open = useOpenIncident();
  if (!data) return <div className="muted">Loading…</div>;
  if (data.seeding)
    return (
      <div className="card pad empty">
        <h2>Generating 21 days of demo data…</h2>
        <p className="muted" style={{ marginTop: 6 }}>
          Simulating a startup, detecting past incidents and training the models. This takes about 15 seconds.
        </p>
      </div>
    );

  const openIncidents: Decision[] = data.metrics.flatMap((m) => m.open_incidents);
  const labelled = data.stats.tp + data.stats.fp;

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Overview</h1>
          <p>Every metric, its expected range right now, and anything that broke.</p>
        </div>
      </div>

      {!!data.maintenance_until && (
        <div className="notice row" style={{ justifyContent: "space-between" }}>
          <span>🔕 Maintenance mode: every alert is paused until {dateTime(data.maintenance_until)}. Incidents are still detected and recorded.</span>
          <button className="btn sm" onClick={async () => { await api.saveSettings({ muted_until: 0 }); reload(); }}>End now</button>
        </div>
      )}

      <div className="grid stats">
        <div className="card pad stat">
          <div className="label">Open incidents</div>
          <div className="value" style={{ color: data.stats.open ? "var(--critical)" : "var(--ok)" }}>{data.stats.open}</div>
          <div className="sub">{data.stats.open ? "needs attention" : "all clear"}</div>
        </div>
        <div className="card pad stat">
          <div className="label">Incidents in last 24 h</div>
          <div className="value">{data.stats.last24}</div>
          <div className="sub">{data.stats.total} all-time</div>
        </div>
        <div className="card pad stat">
          <div className="label">Metrics watched</div>
          <div className="value">{data.metrics.length}</div>
          <div className="sub">{data.metrics.filter((m) => m.model === "custom").length} on custom-trained models</div>
        </div>
        <div className="card pad stat">
          <div className="label">Alert precision (labelled)</div>
          <div className="value">{labelled ? `${Math.round((data.stats.tp / labelled) * 100)}%` : "–"}</div>
          <div className="sub">
            {data.stats.tp} real · {data.stats.fp} false alarms
          </div>
        </div>
      </div>

      {demo && <DemoPanel onInjected={reload} />}

      {openIncidents.length > 0 && (
        <div className="card">
          <div className="card-head">
            <h2>Open incidents</h2>
          </div>
          {openIncidents.map((d) => (
            <div key={d.incident_id} className="incident-row" onClick={() => open(d.incident_id)} role="button" tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && open(d.incident_id)}>
              <div className={`sev-bar ${d.severity}`} />
              <div>
                <div className="title">
                  <span className="mono">{d.metric}</span> {changeText(d)}
                </div>
                <div className="row small muted" style={{ marginTop: 4 }}>
                  <WhereChips where={d.where} />
                  <span>· {num(d.observed)} vs {num(d.expected)} expected · since {ago(d.started_at)}</span>
                </div>
              </div>
              <div className="row">
                <SevChip severity={d.severity} />
                <span className="small muted">{Math.round(d.confidence * 100)}%</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="grid metrics">
        {data.metrics.map((m) => {
          const l = m.latest;
          const dev = l && l.expected ? ((l.value ?? 0) - l.expected) / Math.abs(l.expected) * 100 : null;
          return (
            <div key={m.id} className={`card metric-card ${m.status === "anomaly" ? "anomaly" : ""}`}
              onClick={() => go(`/metric/${m.id}`)} role="link" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && go(`/metric/${m.id}`)}>
              <div className="row">
                <span className="name">{m.name}</span>
                <span className="spacer" />
                <StatusChip status={m.status} />
                {!!m.muted_until && <span className="chip" title={`Alerts muted until ${dateTime(m.muted_until)}`}>🔕 muted</span>}
              </div>
              <div className="row" style={{ alignItems: "baseline" }}>
                <span className="big">{num(l?.value)}</span>
                <span className="vs">
                  expected {num(l?.expected)} {dev !== null && Number.isFinite(dev) && <>({pct(dev)})</>}
                </span>
              </div>
              <Sparkline points={m.sparkline} anomaly={m.status === "anomaly"} />
              <div className="row faint small">
                <span>{m.unit || m.agg}</span>
                <span className="spacer" />
                <span>{m.model === "custom" ? "custom model" : "base model"} · last 6 h</span>
              </div>
            </div>
          );
        })}
        {!data.metrics.length && (
          <div className="card pad empty">
            No metrics yet. <a href="#/connect">Connect a data source</a> or turn on demo mode in Settings.
          </div>
        )}
      </div>
    </div>
  );
}

function DemoPanel({ onInjected }: { onInjected: () => void }) {
  const [scenarios, setScenarios] = useState<{ id: string; label: string }[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();
  const open = useOpenIncident();
  useEffect(() => {
    api.scenarios().then(setScenarios, () => {});
  }, []);
  const inject = async (id: string, label: string) => {
    setBusy(id);
    try {
      const r = await api.inject(id);
      onInjected();
      if (r.incident_id) {
        toast(`Detected: ${label}`);
        open(r.incident_id);
      } else toast("Injected. Kepler hasn't flagged it yet; it will alert once the evidence is strong enough.");
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="card pad demo-panel">
      <div className="row" style={{ marginBottom: 10 }}>
        <h3>Demo: break something</h3>
        <span className="muted small">
          The simulated startup "Orbitly" streams live metrics. Trigger an incident and watch Kepler find where it happened.
        </span>
      </div>
      <div className="row">
        {scenarios.map((s) => (
          <button key={s.id} className="btn sm" disabled={!!busy} onClick={() => inject(s.id, s.label)}>
            {busy === s.id ? "Injecting…" : s.label}
          </button>
        ))}
      </div>
    </div>
  );
}
