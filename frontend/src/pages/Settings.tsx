import { useEffect, useState } from "react";
import { BillingCard } from "../components/Billing";
import { usePoll, useToast } from "../components/ui";
import { api, type Settings as SettingsT } from "../lib/api";
import { ago, dateTime } from "../lib/format";

export function Settings({ onDemoChange }: { onDemoChange: () => void }) {
  const { data, reload } = usePoll(api.settings, 0);
  const log = usePoll(api.notifications, 10000);
  const [f, setF] = useState<SettingsT | null>(null);
  const toast = useToast();
  useEffect(() => {
    if (data) setF(data);
  }, [data]);
  if (!f) return <div className="muted">Loading…</div>;

  const save = async (patch: Partial<SettingsT>) => {
    try {
      const s = await api.saveSettings(patch);
      setF(s);
      toast("Saved");
      if ("demo_mode" in patch) onDemoChange();
    } catch (e) {
      toast((e as Error).message);
    }
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Settings</h1>
          <p>Alerting, Slack, API key, plan and demo mode.</p>
        </div>
      </div>

      <div className="grid two">
        <div className="card pad stack">
          <h2>Alert sensitivity</h2>
          <label className="field">
            Minimum confidence to alert: {Math.round(f.sensitivity * 100)}%
            <input type="range" min={0.2} max={0.95} step={0.05} value={f.sensitivity}
              onChange={(e) => setF({ ...f, sensitivity: Number(e.target.value) })} />
            <span className="hint">Lower = catch more, noisier. Higher = only alert when Kepler is sure.</span>
          </label>
          <label className="field">
            Ignore changes smaller than (%)
            <input type="number" min={0} max={500} value={f.min_change_pct} onChange={(e) => setF({ ...f, min_change_pct: Number(e.target.value) })} />
          </label>
          <div><button className="btn primary" onClick={() => save({ sensitivity: f.sensitivity, min_change_pct: f.min_change_pct })}>Save</button></div>
        </div>

        <div className="card pad stack">
          <h2>Slack alerts</h2>
          <p className="muted small">
            Create an <a href="https://api.slack.com/messaging/webhooks" target="_blank" rel="noreferrer">incoming webhook</a> for your
            #alerts channel and paste it here. New incidents and resolutions are posted with severity, confidence and where it broke.
          </p>
          <label className="field">
            Webhook URL
            <input type="url" value={f.slack_webhook_url} placeholder="https://hooks.slack.com/services/…"
              onChange={(e) => setF({ ...f, slack_webhook_url: e.target.value })} />
          </label>
          <div className="row">
            <button className="btn primary" onClick={() => save({ slack_webhook_url: f.slack_webhook_url })}>Save</button>
            <button className="btn" disabled={!data?.slack_webhook_url} onClick={async () => {
              try { const r = await api.testSlack(); toast(r.ok ? "Test message sent to Slack ✓" : `Slack said: ${r.message}`); }
              catch (e) { toast((e as Error).message); }
            }}>Send test message</button>
          </div>
        </div>

        <div className="card pad stack">
          <h2>API key</h2>
          <p className="muted small">Used by the push API, the Python SDK and the decision endpoint (header <code>X-Kepler-Key</code>).</p>
          <code className="chip accent" style={{ alignSelf: "flex-start" }}>{f.api_key}</code>
          <div><button className="btn danger" onClick={async () => {
            if (!confirm("Rotate the key? Apps using the old key will stop sending data.")) return;
            setF(await api.rotateKey()); toast("New API key generated");
          }}>Rotate key</button></div>
        </div>

        <div className="card pad stack">
          <h2>Demo mode</h2>
          <p className="muted small">Streams a simulated startup's metrics so you can show Kepler to customers without connecting real data.</p>
          <label className="row">
            <input type="checkbox" checked={f.demo_mode} onChange={(e) => save({ demo_mode: e.target.checked })} />
            Stream demo metrics
          </label>
          <div><button className="btn" onClick={async () => {
            if (!confirm("Regenerate 21 days of demo data? Demo incidents and labels will be reset.")) return;
            await api.resetDemo(); toast("Regenerating demo data…"); reload(); onDemoChange();
          }}>Reset demo data</button></div>
        </div>
      </div>

      <div className="card pad">
        <h2>Maintenance mode</h2>
        <p className="muted small" style={{ margin: "4px 0 12px" }}>
          Pause every alert during planned work (migrations, big deploys). Kepler keeps detecting and recording incidents;
          nothing is sent to Slack, PagerDuty, email or webhooks. It ends on its own.
        </p>
        {f.muted_until ? (
          <div className="row">
            <span>🔕 On until {dateTime(f.muted_until)}</span>
            <button className="btn sm" onClick={() => save({ muted_until: 0 })}>End now</button>
          </div>
        ) : (
          <div className="row" style={{ gap: 6 }}>
            {[1, 4, 24].map((h) => (
              <button key={h} className="btn sm" onClick={() => save({ muted_until: Math.floor(Date.now() / 1000) + h * 3600 })}>
                Pause alerts for {h} h
              </button>
            ))}
          </div>
        )}
      </div>

      <BillingCard />

      <div className="card">
        <div className="card-head">
          <div><h2>Alert log</h2><p>Every message Kepler sent (or would have sent) to Slack</p></div>
        </div>
        {(log.data ?? []).map((n) => (
          <div key={n.id} className="incident-row" style={{ cursor: "default" }}>
            <span className={`chip ${n.kind === "resolved" ? "ok" : "anomaly"}`}>{n.kind}</span>
            <div>
              <div>{n.payload.text}</div>
              <div className="small faint">{n.delivered ? "delivered to Slack" : n.error}</div>
            </div>
            <span className="small muted">{ago(n.created_at)}</span>
          </div>
        ))}
        {log.data && !log.data.length && <div className="empty">No alerts sent yet.</div>}
      </div>
    </div>
  );
}
