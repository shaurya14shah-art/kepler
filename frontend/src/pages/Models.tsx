import { useState } from "react";
import { ProfileChart } from "../components/Charts";
import { TierSection } from "../components/Tiers";
import { usePoll, useToast } from "../components/ui";
import { api, type TrainReport } from "../lib/api";
import { ago } from "../lib/format";

const FEATURE_NAMES: Record<string, string> = {
  abs_z: "size of deviation (z)",
  abs_base_z: "deviation vs base model",
  log_rel_change: "% change",
  duration: "how long it lasted",
  hour_sin: "time of day",
  hour_cos: "time of day",
  weekend: "weekend",
  spike: "spike vs drop",
  is_mean: "averaged metric",
};

export function Models() {
  const { data, reload } = usePoll(api.models, 0);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<TrainReport | null>(null);
  const toast = useToast();

  const train = async () => {
    setBusy(true);
    try {
      const r = await api.train();
      setReport(r);
      toast("Models retrained on your latest data and labels");
      reload();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!data) return <div className="muted">Loading…</div>;
  const fb = data.feedback;

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Models</h1>
          <p>Choose how hard Kepler thinks (Orbit, Area or Time), then see what each layer has learned.</p>
        </div>
        <button className="btn primary" onClick={train} disabled={busy}>{busy ? "Training…" : "Retrain now"}</button>
      </div>

      <TierSection />

      <div className="grid two">
        <div className="card pad stack">
          <h2>1 · Baseline: what should the metric be?</h2>
          <p className="muted small">
            <b>Shared base model</b> works for any customer from day one: the trimmed average of the same time of day on similar
            days (weekday vs weekend) over the last 2 weeks, with robust noise estimates and exact Poisson tests for counts.
          </p>
          <p className="muted small">
            <b>Custom model</b> is trained per metric and per slice on your own history (7+ days): a learned weekly shape, a
            noise profile for each time of day, and past incidents excluded from training.
          </p>
        </div>
        <div className="card pad stack">
          <h2>2 · Filter: is this worth waking someone?</h2>
          <p className="muted small">
            Every deviation gets a statistical prior. Once you've labelled 8+ alerts (both kinds), a classifier trained on your 👍/👎
            is blended in. Its weight grows with the number of labels (up to 60%).
          </p>
          <div className="row">
            <span className={`chip ${fb.active ? "ok" : ""}`}>{fb.active ? "learned filter active" : "prior only"}</span>
            <span className="chip">{data.labels.pos} 👍 · {data.labels.neg} 👎 · {data.labels.unl} unlabelled</span>
            {fb.active && <span className="chip accent">weight {Math.round(fb.weight * 100)}%</span>}
            {fb.cv_accuracy != null && <span className="chip accent">cross-validated accuracy {Math.round(fb.cv_accuracy * 100)}%</span>}
          </div>
          {!fb.active && fb.status && <p className="small muted">{fb.status}</p>}
          {fb.top_features && (
            <div className="small">
              <div className="muted" style={{ marginBottom: 4 }}>What your team's labels taught it:</div>
              {fb.top_features.map((f) => (
                <div key={f.feature}>
                  {f.weight > 0 ? "↑ more likely real when higher:" : "↓ less likely real when higher:"} <b>{FEATURE_NAMES[f.feature] ?? f.feature}</b>{" "}
                  <span className="faint">({f.weight > 0 ? "+" : ""}{f.weight})</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card table-wrap">
        <table>
          <thead>
            <tr><th>Metric</th><th>Model</th><th>Learned weekly shape</th><th>Slices trained</th><th>Trained on</th><th>Updated</th></tr>
          </thead>
          <tbody>
            {data.metrics.map((m) => (
              <tr key={m.metric_id} className="clickable" onClick={() => (window.location.hash = `/metric/${m.metric_id}`)}>
                <td className="mono">{m.metric}</td>
                <td><span className={`chip ${m.kind === "custom" ? "accent" : ""}`}>{m.kind === "custom" ? `custom · ${m.period}` : "base (shared)"}</span></td>
                <td>{m.profile ? <ProfileChart profile={m.profile} /> : <span className="faint small">needs 7 days of data</span>}</td>
                <td>{m.slices_trained ? m.slices_trained - 1 : "–"}</td>
                <td>{m.trained_days ? `${m.trained_days} days` : "–"}</td>
                <td className="muted small">{m.trained_at ? ago(m.trained_at) : "never"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {report && (
        <div className="card pad">
          <h3 style={{ marginBottom: 8 }}>Last training run</h3>
          <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
            {report.metrics.map((m) => (
              <li key={m.metric}><span className="mono">{m.metric}</span>: {m.status}{m.slices_trained ? ` (${m.slices_trained} series)` : ""}</li>
            ))}
            <li>feedback filter: {report.feedback.status} ({report.feedback.n_labels} labels)</li>
          </ul>
        </div>
      )}
    </div>
  );
}
