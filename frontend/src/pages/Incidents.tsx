import { useState } from "react";
import { useOpenIncident } from "../components/IncidentDrawer";
import { SevChip, StatusChip, WhereChips, usePoll, useToast } from "../components/ui";
import { api } from "../lib/api";
import { changeText, dateTime, duration, num } from "../lib/format";

export function Incidents() {
  const [status, setStatus] = useState<"" | "open" | "resolved">("");
  const [unlabelledOnly, setUnlabelledOnly] = useState(false);
  const open = useOpenIncident();
  const { data, error, reload } = usePoll(() => api.incidents(status || undefined), 10000, [status]);
  const models = usePoll(() => api.models(), 60000, []);
  const toast = useToast();
  const rows = (data ?? []).filter((d) => !unlabelledOnly || d.feedback === null);
  const fb = models.data?.feedback;
  const MIN_LABELS = 8; // (engine/classifier.py: the filter trains from 8 labels with both 👍 and 👎)

  async function label(e: React.MouseEvent, id: number, current: number | null, v: number) {
    e.stopPropagation(); // (the row opens the incident)
    const next = current === v ? null : v;
    await api.feedback(id, next);
    reload();
    models.reload();
    if (next !== null) toast(next === 1 ? "Marked real. Kepler learns from this." : "Marked a false alarm. Kepler learns to stay quiet on alerts like it.");
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Incidents</h1>
          <p>Every decision Kepler made. Label them 👍/👎 to train your workspace's alert filter.</p>
          {fb && (
            <p className="small muted" style={{ marginTop: 2 }}>
              {fb.active
                ? `Learned filter on: ${fb.n_labels} labels, trusted at ${Math.round(fb.weight * 100)}%. More labels, more trust.`
                : `Learned filter off: ${fb.n_labels} of ${MIN_LABELS} labels so far (it needs both 👍 and 👎). Then run Train on the Models page.`}
            </p>
          )}
        </div>
        <div className="row">
          {(["", "open", "resolved"] as const).map((s) => (
            <button key={s} className={`btn sm ${status === s ? "on" : ""}`} onClick={() => setStatus(s)}>{s || "all"}</button>
          ))}
          <label className="row small muted" style={{ gap: 6 }}>
            <input type="checkbox" checked={unlabelledOnly} onChange={(e) => setUnlabelledOnly(e.target.checked)} /> unlabelled only
          </label>
        </div>
      </div>
      {error && <div className="notice err">{error}</div>}
      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>Severity</th><th>Metric</th><th>Change</th><th>Where</th><th>Started</th><th>Duration</th><th>Confidence</th><th>Status</th><th>Label</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.incident_id} className="clickable" onClick={() => open(d.incident_id)}>
                <td><SevChip severity={d.severity} /></td>
                <td className="mono">
                  {d.metric}
                  {!!d.related?.length && <div className="faint small" title={d.related.map((r) => `#${r.incident_id} ${r.metric}`).join(", ")}>+{d.related.length} at the same time</div>}
                </td>
                <td>
                  {changeText(d)}
                  <div className="faint small">{num(d.observed)} vs {num(d.expected)}</div>
                </td>
                <td><WhereChips where={d.where} /></td>
                <td className="small">{dateTime(d.started_at)}</td>
                <td className="small muted">{duration(d.started_at, d.last_seen_at)}</td>
                <td>{Math.round(d.confidence * 100)}%</td>
                <td><StatusChip status={d.status} /></td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className={`btn sm ${d.feedback === 1 ? "on" : ""}`} aria-label="Real incident" title="Real incident"
                    onClick={(e) => label(e, d.incident_id, d.feedback, 1)}>👍</button>{" "}
                  <button className={`btn sm ${d.feedback === 0 ? "on" : ""}`} aria-label="False alarm" title="False alarm"
                    onClick={(e) => label(e, d.incident_id, d.feedback, 0)}>👎</button>
                </td>
              </tr>
            ))}
            {data && !rows.length && <tr><td colSpan={9} className="empty">No incidents match.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
