import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type Note } from "../lib/api";
import { ago, changeText, dateTime, duration, num, pct, whereText } from "../lib/format";
import { MetricChart } from "./Charts";
import { TierBadge } from "./Tiers";
import { Drawer, JsonView, SevChip, StatusChip, go, useToast } from "./ui";

const Ctx = createContext<(id: number) => void>(() => {});
export const useOpenIncident = () => useContext(Ctx);

type Detail = Awaited<ReturnType<typeof api.incident>>;

export function IncidentProvider({ children, onChange }: { children: ReactNode; onChange?: () => void }) {
  const [id, setId] = useState<number | null>(null);
  const close = useCallback(() => setId(null), []);
  return (
    <Ctx.Provider value={setId}>
      {children}
      <Drawer open={id !== null} onClose={close} label="Incident details">
        {id !== null && <IncidentDetail id={id} onClose={close} onChange={onChange} />}
      </Drawer>
    </Ctx.Provider>
  );
}

function IncidentDetail({ id, onClose, onChange }: { id: number; onClose: () => void; onChange?: () => void }) {
  const [data, setData] = useState<Detail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showJson, setShowJson] = useState(false);
  const toast = useToast();
  const openOther = useOpenIncident();

  useEffect(() => {
    api.incident(id).then(setData, (e) => setErr(e.message));
  }, [id]);

  if (err) return <div className="drawer-body notice err">{err}</div>;
  if (!data) return <div className="drawer-body muted">Loading…</div>;
  const d = data.decision;

  const label = async (v: number | null) => {
    await api.feedback(d.incident_id, v);
    setData({ ...data, decision: { ...d, feedback: v } });
    toast(v === 1 ? "Marked as a real incident. Kepler will learn from this." : v === 0 ? "Marked as a false alarm. Kepler will learn to stay quiet on alerts like this." : "Label cleared.");
    onChange?.();
  };

  return (
    <>
      <div className="drawer-head">
        <div style={{ flex: 1 }}>
          <div className="row" style={{ gap: 8 }}>
            <SevChip severity={d.severity} />
            <StatusChip status={d.status} />
            <TierBadge tier={d.tier} />
            <span className="faint small">#{d.incident_id}</span>
          </div>
          <h2 style={{ marginTop: 6 }}>
            <span className="mono">{d.metric}</span>{" "}
            {d.kind === "no_data" ? `stopped reporting (${changeText(d)})` : `${d.direction === "spike" ? "spiked" : "dropped"} ${pct(d.change_pct)}`}
          </h2>
          <p className="muted small">
            where <b>{whereText(d.where)}</b> · started {dateTime(d.started_at)} ({ago(d.started_at)}) · lasted{" "}
            {duration(d.started_at, d.last_seen_at)}
          </p>
        </div>
        <button className="btn sm" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>
      <div className="drawer-body">
        <div className="kv">
          <div>
            <div className="k">Observed</div>
            <div className="v">{num(d.observed)}</div>
          </div>
          <div>
            <div className="k">Expected</div>
            <div className="v">{num(d.expected)}</div>
            <div className="faint small">
              range {num(d.expected_range[0])}–{num(d.expected_range[1])}
            </div>
          </div>
          <div>
            <div className="k">Confidence</div>
            <div className="v">{Math.round(d.confidence * 100)}%</div>
          </div>
          <div>
            <div className="k">z-score</div>
            <div className="v">{d.z_score.toFixed(1)}</div>
          </div>
        </div>

        <div className="card pad">
          <div className="row" style={{ marginBottom: 8 }}>
            <h3>{d.slice ? `${d.metric} · ${d.slice}` : d.metric}</h3>
            <span className="spacer" />
            <span className="faint small">dashed = expected, shaded = normal range</span>
          </div>
          <MetricChart points={data.points} incidents={[d]} highlight={d.incident_id} unit={d.unit} height={240} />
        </div>

        {!!d.related?.length && (
          <div className="card pad">
            <h3 style={{ marginBottom: 6 }}>At the same time</h3>
            <p className="muted small" style={{ margin: "0 0 8px" }}>Started within 15 minutes of this one: likely the same problem.</p>
            <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
              {d.related.map((r) => (
                <li key={r.incident_id} style={{ marginBottom: 4 }}>
                  <button className="btn sm" onClick={() => openOther(r.incident_id)}>#{r.incident_id}</button>{" "}
                  <span className="mono">{r.metric}{r.slice ? ` · ${r.slice}` : ""}</span> {changeText(r)}{" "}
                  <span className="faint">({r.severity}, {r.status})</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="card pad">
          <h3 style={{ marginBottom: 10 }}>Where it broke</h3>
          <div className="where-bars">
            {d.where.map((w) => (
              <div className="where-bar" key={`${w.dimension}=${w.value}`}>
                <span className="mono">{w.dimension === "*" ? "all segments" : `${w.dimension}=${w.value}`}</span>
                <div className="track" title={`${Math.round(w.share_of_change * 100)}% of the total change`}>
                  <div className="fill" style={{ width: `${Math.min(100, Math.max(4, w.share_of_change * 100))}%` }} />
                </div>
                <span className="small muted">{pct(w.change_pct)}</span>
              </div>
            ))}
          </div>
          <p className="faint small" style={{ marginTop: 10 }}>
            Bar = share of the total deviation explained by this slice. % = how much the slice itself changed vs its normal.
          </p>
        </div>

        {d.reasoning && (
          <div className="card pad time-reasoning">
            <div className="row" style={{ marginBottom: 8 }}>
              <h3>Time's reasoning</h3>
              <span className="spacer" />
              {d.reasoning.impact_text && <span className="chip anomaly">{d.reasoning.impact_text}</span>}
            </div>
            <ol className="small" style={{ margin: 0, paddingLeft: 20, lineHeight: 1.7 }}>
              {d.reasoning.steps.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
            {d.reasoning.related.length > 0 && (
              <div className="row" style={{ marginTop: 10, gap: 6 }}>
                <span className="small muted">Linked:</span>
                {d.reasoning.related.map((r) => (
                  <span key={r.incident_id} className={`chip ${r.likely_same_cause ? "where" : ""}`}
                    title={r.where.join(", ")}>#{r.incident_id} {r.metric} {r.direction === "spike" ? "▲" : "▼"}</span>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="card pad">
          <h3>Was this a real incident?</h3>
          <p className="muted small" style={{ margin: "4px 0 12px" }}>
            Your answer trains this workspace's alert filter. Over time Kepler learns which alerts your team cares about.
          </p>
          <div className="row">
            <button className={`btn ${d.feedback === 1 ? "on" : ""}`} onClick={() => label(d.feedback === 1 ? null : 1)}>
              👍 Real incident
            </button>
            <button className={`btn ${d.feedback === 0 ? "on" : ""}`} onClick={() => label(d.feedback === 0 ? null : 0)}>
              👎 False alarm
            </button>
            <span className="spacer" />
            <button className="btn sm" onClick={() => { onClose(); go(`/metric/${d.metric_id}`); }}>
              Open metric →
            </button>
          </div>
        </div>

        <Notes incidentId={d.incident_id} notes={data.notes ?? []} onChange={(notes) => setData({ ...data, notes })} />

        <div className="card pad">
          <h3 style={{ marginBottom: 6 }}>How Kepler decided</h3>
          <ul className="small muted" style={{ margin: 0, paddingLeft: 18 }}>
            <li>Baseline: {d.model.baseline}</li>
            <li>
              Filter: {d.model.filter}
              {d.model.prior != null && (
                <>
                  {" "}
                  (statistical prior {Math.round(d.model.prior * 100)}%
                  {d.model.learned != null && <>, learned {Math.round(d.model.learned * 100)}% at weight {d.model.weight}</>})
                </>
              )}
            </li>
            <li>
              Slack:{" "}
              {data.notifications.length
                ? data.notifications.map((n) => `${n.kind} ${n.delivered ? "✓ delivered" : `(${n.error})`}`).join(", ")
                : "not sent (historical incident)"}
            </li>
          </ul>
        </div>

        <div>
          <button className="btn sm" onClick={() => setShowJson(!showJson)}>
            {showJson ? "Hide" : "Show"} decision JSON
          </button>
          {showJson && (
            <div style={{ marginTop: 10 }}>
              <JsonView value={{ ...d, feedback: undefined, metric_id: undefined, unit: undefined }} />
            </div>
          )}
        </div>
      </div>
    </>
  );
}

/** What the team found or did about this incident ("rolled back deploy 4.2"): kept with it for everyone to see. */
function Notes({ incidentId, notes, onChange }: { incidentId: number; notes: Note[]; onChange: (n: Note[]) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  async function add() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      onChange((await api.addNote(incidentId, text.trim())).notes);
      setText("");
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="card pad">
      <h3 style={{ marginBottom: 6 }}>Notes</h3>
      {notes.length ? (
        <ul className="small" style={{ margin: "0 0 10px", paddingLeft: 18 }}>
          {notes.map((n) => (
            <li key={n.id} style={{ marginBottom: 4 }}>
              <span className="faint">{dateTime(n.created_at)}</span> · {n.text}{" "}
              <button className="btn sm" aria-label="Delete note" onClick={async () => onChange((await api.deleteNote(incidentId, n.id)).notes)}>
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small" style={{ margin: "0 0 10px" }}>What did you find or do? Notes stay with the incident.</p>
      )}
      <div className="row" style={{ gap: 6 }}>
        <textarea
          aria-label="New note"
          rows={2}
          maxLength={2000}
          placeholder="e.g. rolled back deploy 4.2"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => (e.metaKey || e.ctrlKey) && e.key === "Enter" && add()}
          style={{ flex: 1, minWidth: 0 }}
        />
        <button className="btn" disabled={busy || !text.trim()} onClick={add}>Add note</button>
      </div>
    </div>
  );
}
