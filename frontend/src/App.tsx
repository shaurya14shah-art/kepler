import { useEffect, useState } from "react";
import { IncidentProvider, useOpenIncident } from "./components/IncidentDrawer";
import { SignIn } from "./components/SignIn";
import { ToastProvider, usePoll, useRoute } from "./components/ui";
import { api } from "./lib/api";
import { Connect } from "./pages/Connect";
import { Incidents } from "./pages/Incidents";
import { MetricPage } from "./pages/MetricPage";
import { Models } from "./pages/Models";
import { Overview } from "./pages/Overview";
import { Settings } from "./pages/Settings";

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="6" fill="var(--accent)" />
      <ellipse cx="16" cy="16" rx="14" ry="6" fill="none" stroke="var(--accent)" strokeWidth="2" transform="rotate(-25 16 16)" />
      <circle cx="28" cy="10.5" r="2" fill="var(--critical)" />
    </svg>
  );
}

/** #/incident/40 deep links (used by `kepler open incident 40` and the terminal app) */
function IncidentDeepLink({ id }: { id: number }) {
  const open = useOpenIncident();
  useEffect(() => {
    if (id) open(id);
  }, [id, open]);
  return null;
}

export default function App() {
  const route = useRoute();
  const overview = usePoll(api.overview, 10000);
  const [demo, setDemo] = useState(true);
  const refreshDemo = () => api.settings().then((s) => setDemo(s.demo_mode), () => {});
  const [auth, setAuth] = useState<{ required: boolean; signedIn: boolean } | null>(null);
  useEffect(() => {
    refreshDemo();
    api.session().then((s) => setAuth({ required: s.auth_required, signedIn: s.signed_in }), () => {});
    const needSignIn = () => setAuth({ required: true, signedIn: false });
    window.addEventListener("kepler:signin", needSignIn);
    return () => window.removeEventListener("kepler:signin", needSignIn);
  }, []);

  const page = route[0] ?? "";
  const open = overview.data?.stats.open ?? 0;
  const nav = [
    ["", "Overview"],
    ["incidents", "Incidents"],
    ["models", "Models"],
    ["connect", "Integrations"],
    ["settings", "Settings"],
  ] as const;

  let body;
  if (page === "metric" && route[1]) body = <MetricPage id={Number(route[1])} />;
  else if (page === "incidents" || page === "incident") body = <Incidents />;
  else if (page === "models") body = <Models />;
  else if (page === "connect") body = <Connect />;
  else if (page === "settings") body = <Settings onDemoChange={() => { refreshDemo(); overview.reload(); }} />;
  else body = <Overview data={overview.data} reload={overview.reload} demo={demo} />;

  if (auth?.required && !auth.signedIn) return <SignIn logo={<Logo />} />;

  return (
    <ToastProvider>
      <IncidentProvider onChange={overview.reload}>
        <div className="shell">
          <aside className="sidebar">
            <div className="brand">
              <Logo />
              <div>
                Kepler
                <small>metric watchdog</small>
              </div>
            </div>
            <nav className="nav">
              {nav.map(([path, label]) => (
                <a key={path} href={`#/${path}`} className={page === path || (page === "metric" && path === "") || (page === "incident" && path === "incidents") ? "active" : ""}>
                  {label}
                  {path === "incidents" && open > 0 && <span className="count">{open}</span>}
                </a>
              ))}
            </nav>
            <div className="sidebar-foot">
              {overview.error ? (
                <span style={{ color: "var(--critical)" }}>API unreachable</span>
              ) : (
                <>
                  <span className="live-dot" />
                  {demo ? "Live · demo data" : "Live"}
                </>
              )}
              {auth?.required && (
                <div style={{ marginTop: 8 }}>
                  <a href="#/" onClick={async (e) => { e.preventDefault(); await api.signOut(); location.reload(); }}>Sign out</a>
                </div>
              )}
            </div>
          </aside>
          <main>{body}</main>
          {page === "incident" && route[1] && <IncidentDeepLink id={Number(route[1])} />}
        </div>
      </IncidentProvider>
    </ToastProvider>
  );
}
