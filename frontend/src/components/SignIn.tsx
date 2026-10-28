import { useState } from "react";
import { api } from "../lib/api";

/** Shown when the server's access gate is on and this browser isn't signed in. */
export function SignIn({ logo }: { logo: React.ReactNode }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.signIn(key.trim());
      location.reload();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="signin">
      <form className="card pad stack signin-card" onSubmit={submit}>
        <div className="row">
          {logo}
          <div>
            <h1 style={{ margin: 0 }}>Sign in to Kepler</h1>
            <p className="muted small" style={{ margin: 0 }}>This workspace is protected by an access key.</p>
          </div>
        </div>
        <label className="field">
          Access key
          <input type="password" autoFocus autoComplete="current-password" placeholder="kp_…" value={key}
            onChange={(e) => setKey(e.target.value)} />
          <span className="hint">
            Run <code>kepler key</code> on the server to see it (it's also printed when <code>kepler serve</code> starts).
          </span>
        </label>
        {error && <div className="signin-error">{error}</div>}
        <div><button className="btn primary" disabled={busy || !key.trim()}>{busy ? "Signing in…" : "Sign in"}</button></div>
      </form>
    </div>
  );
}
