import { useState } from "react";
import { api, type CompareResp, type Tier, type TierId, type TiersResp } from "../lib/api";
import { usePoll, useToast } from "./ui";

const GLYPH: Record<TierId, string> = { orbit: "◯", area: "◐", time: "◉" };

export function TierBadge({ tier }: { tier?: TierId | null }) {
  if (!tier) return null;
  return <span className={`chip tier-${tier}`} title={`Model: ${tier}`}>{GLYPH[tier]} {tier[0].toUpperCase() + tier.slice(1)}</span>;
}

function Meter({ label, value, max, good, text }: { label: string; value: number; max: number; good: "low" | "high"; text: string }) {
  const pct = max > 0 ? Math.max(4, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div className="meter">
      <span className="meter-label">{label}</span>
      <span className="meter-track"><span className={`meter-fill ${good}`} style={{ width: `${pct}%` }} /></span>
      <span className="meter-text">{text}</span>
    </div>
  );
}

export function PaywallNote({ note }: { note: string }) {
  return <div className="notice beta">🧪 {note}</div>;
}

/** The three Kepler models, measured side by side, with a picker for the workspace default. */
export function TierCards({ data, onChange }: { data: TiersResp; onChange: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<TierId | null>(null);
  const tiers = [...data.tiers].sort((a, b) => b.rank - a.rank); // worst → best, left → right
  const maxMs = Math.max(...tiers.map((t) => t.benchmark?.eval_ms_per_metric ?? 0));
  const choose = async (t: Tier) => {
    setBusy(t.id);
    try {
      await api.setDefaultTier(t.id);
      toast(`${t.name} is now the default model. Metrics without their own setting switch on the next check.`);
      onChange();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="tier-grid">
      {tiers.map((t) => {
        const b = t.benchmark;
        const active = data.default === t.id;
        return (
          <div key={t.id} className={`card pad tier-card tier-${t.id} ${active ? "active" : ""}`}>
            <div className="row">
              <span className="tier-glyph" aria-hidden="true">{GLYPH[t.id]}</span>
              <div style={{ flex: 1 }}>
                <h2>{t.name}</h2>
                <div className="faint small">{t.law}</div>
              </div>
              {t.rank === 1 && <span className="chip accent">best</span>}
              {t.rank === 3 && <span className="chip">leanest</span>}
            </div>
            <p className="small muted" style={{ minHeight: 54 }}>{t.tagline}</p>
            {b ? (
              <div className="stack" style={{ gap: 6 }}>
                <Meter label="cost" value={b.eval_ms_per_metric} max={maxMs} good="low" text={`${b.eval_ms_per_metric.toFixed(0)} ms/check`} />
                <Meter label="speed" value={maxMs / b.eval_ms_per_metric} max={maxMs / Math.min(...tiers.map((x) => x.benchmark?.eval_ms_per_metric ?? maxMs))} good="high"
                  text={`${(maxMs / b.eval_ms_per_metric).toFixed(1)}× ${t.id === "time" ? "(baseline)" : "faster"}`} />
                <Meter label="reasoning" value={4 - t.rank} max={3} good="high" text={["", "deepest", "solid", "basic"][t.rank]} />
                <Meter label="accuracy" value={b.caught + b.hard_cases_caught} max={b.real + b.hard_cases} good="high"
                  text={`${b.caught}/${b.real} + ${b.hard_cases_caught}/${b.hard_cases} hard`} />
              </div>
            ) : (
              <p className="faint small">Not benchmarked yet: run stress/bench_tiers.py --write</p>
            )}
            <ul className="small tier-features">
              <li>{t.custom_models ? "✓ trained on your data, per metric" : "· shared baseline, no training"}</li>
              <li>{t.slices ? `✓ watches every slice${t.combos ? ` + ${t.combos} exact segments` : ""}` : "· whole metrics only"}</li>
              <li>{t.learned_filter ? "✓ learns from your 👍 / 👎" : "· statistical filter only"}</li>
              <li>{t.reasoning ? "✓ links incidents, impact, reasoning chain" : "· standard explanation"}</li>
              {t.pooling.some((w) => w >= 24) && <li>✓ slow-burn detection (2–4 h)</li>}
            </ul>
            <div className="row" style={{ marginTop: "auto" }}>
              {t.price_preview && (
                <div>
                  <div className="tier-price">{t.price_preview}</div>
                  <div className="faint small">preview · free in beta</div>
                </div>
              )}
              <span className="spacer" />
              <button className={`btn ${active ? "on" : "primary"}`} disabled={active || !!busy} onClick={() => choose(t)}>
                {active ? "Default" : busy === t.id ? "Switching…" : "Use as default"}
              </button>
            </div>
            <div className="faint small">{t.metrics} metric{t.metrics === 1 ? "" : "s"} on {t.name}</div>
          </div>
        );
      })}
    </div>
  );
}

/** Model section of the Models page: cards (+ estimated bill only if payments are ever enabled). */
export function TierSection() {
  const { data, reload } = usePoll(api.tiers, 0);
  if (!data) return null;
  return (
    <div className="stack">
      <div className="row">
        <div>
          <h2>Choose a model</h2>
          <p className="muted small">Three detection models named after Kepler's laws. Pick a default; any metric can override it.</p>
        </div>
        <span className="spacer" />
        {data.monthly_preview && (
          <div style={{ textAlign: "right" }}>
            <div className="small muted">Estimated monthly bill (preview)</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>
              ${data.monthly_preview.amount.toFixed(0)} <span className="faint small" style={{ fontWeight: 500 }}>→ $0 charged</span>
            </div>
          </div>
        )}
      </div>
      <PaywallNote note={data.paywall.note} />
      <TierCards data={data} onChange={reload} />
      <p className="faint small">
        Measured on Kepler's simulated startup (8 real incidents + 3 hard cases: two slow burns and one iOS × EU-only
        failure), {data.tiers[0]?.benchmark?.measured_at ?? "not yet"}. Cost = scoring time per metric per 5-minute check.
      </p>
    </div>
  );
}

/** Run all three models on one metric right now. */
export function ComparePanel({ metricId, current, onSetTier }: { metricId: number; current?: TierId; onSetTier: () => void }) {
  const [res, setRes] = useState<CompareResp | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const run = async () => {
    setBusy(true);
    try {
      setRes(await api.compare(metricId));
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const setTier = async (t: TierId | "default") => {
    await api.setMetricTier(metricId, t);
    toast(t === "default" ? "This metric now follows the workspace default model" : `This metric now uses ${t}`);
    onSetTier();
  };
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2>Compare models</h2>
          <p>Run Orbit, Area and Time on this metric's latest data right now, cold.</p>
        </div>
        <button className="btn" onClick={run} disabled={busy}>{busy ? "Running…" : res ? "Run again" : "Run all three"}</button>
      </div>
      {res && (() => {
        const priced = res.tiers.some((t) => t.price_preview);
        return (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Model</th><th>Verdict</th><th>Most unusual series</th><th>Confidence</th><th>Series</th><th>Time</th>{priced && <th>Price (preview)</th>}<th /></tr></thead>
            <tbody>
              {res.tiers.map((t) => (
                <tr key={t.tier}>
                  <td><TierBadge tier={t.tier} /></td>
                  <td><span className={`chip ${t.verdict === "anomaly" ? "anomaly" : "ok"}`}>{t.verdict}</span></td>
                  <td className="mono small">{t.top?.series ?? "–"}</td>
                  <td>{t.top ? `${Math.round(t.top.confidence * 100)}%` : "–"}</td>
                  <td>{t.series_watched}</td>
                  <td>{t.ms.toFixed(0)} ms</td>
                  {priced && <td className="small">{t.price_preview}</td>}
                  <td>
                    {res.current === t.tier ? <span className="chip accent">in use</span>
                      : <button className="btn sm" onClick={() => setTier(t.tier)}>Use for this metric</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        );
      })()}
      {current && (
        <div className="row small muted" style={{ padding: "10px 18px" }}>
          This metric uses <TierBadge tier={current} />
          <button className="btn sm" onClick={() => setTier("default")}>Follow workspace default</button>
        </div>
      )}
    </div>
  );
}
