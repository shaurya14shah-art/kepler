export type Where = { dimension: string; value: string; share_of_change: number; change_pct: number | null };

export type TierId = "orbit" | "area" | "time";

export type TierBenchmark = {
  recall: number; caught: number; real: number; hard_cases_caught: number; hard_cases: number; hard_caught: string[];
  noise_per_week: number; root_cause_accuracy: number; series_per_metric: number; eval_ms_per_metric: number;
  cpu_seconds_per_metric_month: number; train_seconds: number; reasoning_ms_per_incident: number | null; measured_at: string;
};

export type Tier = {
  id: TierId; name: string; law: string; tagline: string; custom_models: boolean; slices: boolean; pooling: number[];
  learned_filter: boolean; drilldown: number; reasoning: boolean; combos: number;
  price_preview?: string; price_per_metric_month?: number; rank: number; metrics: number; benchmark: TierBenchmark | null;
};

export type TiersResp = {
  default: TierId;
  paywall: { enabled: boolean; note: string };
  tiers: Tier[];
  monthly_preview?: { amount: number; charged: number; currency: string };  // only when payments are enabled
};

export type CompareResp = {
  metric: string; at: number; current: TierId; paywall: { enabled: boolean; note: string };
  tiers: { tier: TierId; name: string; series_watched: number; ms: number; verdict: "anomaly" | "normal";
    top: { series: string; anomaly: boolean; confidence: number; observed: number | null; expected: number | null; z: number | null } | null;
    price_preview?: string }[];
};

export type Related = {
  incident_id: number; metric: string; slice: string | null; kind?: IncidentKind; direction: string; severity: string;
  status: string; started_at: number; change_pct: number | null;
};

export type Decision = {
  related?: Related[]; // incidents (any metric) that started within 15 minutes of this one
  kind?: IncidentKind; // "no_data": the metric stopped reporting
  silent_since?: number | null;
  decision: "anomaly";
  incident_id: number;
  metric: string;
  metric_id: number;
  unit: string;
  slice: string | null;
  status: "open" | "resolved";
  direction: "spike" | "drop";
  severity: "critical" | "high" | "medium";
  confidence: number;
  observed: number;
  expected: number;
  expected_range: [number, number];
  change_pct: number;
  z_score: number;
  where: Where[];
  started_at: number;
  last_seen_at: number;
  model: { baseline?: string; filter?: string; prior?: number; learned?: number | null; weight?: number; tier?: string; impact?: number };
  feedback: number | null;
  tier?: TierId;
  reasoning?: {
    impact: number | null;
    impact_text: string | null;
    steps: string[];
    related: { incident_id: number; metric: string; direction: string; severity: string; started_at: number; shared: string[]; where: string[]; likely_same_cause: boolean }[];
  };
};

export type Point = { ts: number; value: number | null; expected: number | null; lower?: number | null; upper?: number | null; z?: number | null };

export type IncidentKind = "anomaly" | "no_data";

export type Note = { id: number; text: string; created_at: number };

export type MetricSummary = {
  id: number;
  name: string;
  unit: string;
  agg: "sum" | "mean";
  source: string;
  description: string;
  bad_direction: "up" | "down" | "both";
  status: "ok" | "anomaly" | "stale";
  model: "base" | "custom";
  model_label: string;
  tier?: TierId;
  tier_override?: TierId | null;
  muted_until?: number; // alerts paused until (epoch seconds); 0 = not muted
  latest: Point | null;
  last_ts: number | null;
  sparkline: Point[];
  open_incidents: Decision[];
};

export type Overview = {
  metrics: MetricSummary[];
  stats: { open: number; last24: number; tp: number; fp: number; total: number };
  seeding: boolean;
  now: number;
  maintenance_until?: number; // maintenance mode (Settings): every alert paused until then; 0 = off
};

export type Series = {
  metric: MetricSummary & Record<string, unknown>;
  slice: string;
  slices: string[];
  model: string;
  model_kind: string;
  tier: TierId;
  reports_every_s?: number; // how often the metric reports (300 = every 5 min); coarser metrics are judged per reading
  points: Point[];
  incidents: Decision[];
};

export type Settings = {
  sensitivity: number;
  min_change_pct: number;
  slack_webhook_url: string;
  demo_mode: boolean;
  api_key: string;
  bucket_seconds: number;
  model_tier: TierId;
  muted_until: number; // maintenance mode: every alert paused until then (epoch seconds); 0 = off
};

export type IntegrationField = {
  name: string;
  label: string;
  kind: "text" | "password" | "url" | "number" | "select" | "textarea";
  default: string;
  required: boolean;
  help: string;
  options: string[];
};

export type Integration = {
  type: string;
  label: string;
  category: string;
  direction: "pull" | "push" | "destination";
  summary: string;
  fields: IntegrationField[];
  default_agg: "sum" | "mean";
  default_bad: "up" | "down" | "both";
  docs: string;
};

export type Destination = {
  id: number;
  type: string;
  label: string;
  name: string;
  min_severity: string;
  enabled: number;
  last_status: string;
  config: Record<string, string>;
};

export type Connector = {
  id: number;
  type: string;
  label?: string;
  name: string;
  interval_s: number;
  enabled: number;
  last_run: number;
  last_status: string;
  config: Record<string, string>;
};

export type Plan = {
  id: string;
  name: string;
  tagline: string;
  features: string[];
  amount: number | null; // smallest currency unit; null while billing is off
  currency: string;
  interval: string;
  for_sale: boolean;
};

export type Billing = {
  enabled: boolean;
  provider: string;
  mode: "disabled" | "test" | "live" | "";
  message: string;
  blockers: string[];
  key_id: string | null;
  plan: string;
  plans: Plan[];
};

export type CheckoutStart = {
  key_id: string;
  order_id?: string;
  subscription_id?: string;
  amount?: number;
  currency?: string;
  plan: string;
  name: string;
  description: string;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init?.body instanceof FormData ? init?.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (res.status === 401 && !path.startsWith("/api/session")) {
    window.dispatchEvent(new Event("kepler:signin")); // the access gate is on and this browser isn't signed in
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

const post = <T,>(path: string, body?: unknown) =>
  req<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => req<{ seeding: boolean; last_error: string | null }>("/api/health"),
  overview: () => req<Overview>("/api/overview"),
  series: (id: number, hours: number, slice = "") =>
    req<Series>(`/api/metrics/${id}/series?hours=${hours}&slice=${encodeURIComponent(slice)}`),
  breakdown: (id: number) =>
    req<{ slices: { slice: string; dimension: string; value: string; observed: number | null; expected: number | null; z: number | null; change_pct: number | null }[] }>(
      `/api/metrics/${id}/breakdown`,
    ),
  patchMetric: (id: number, body: Partial<Pick<MetricSummary, "unit" | "description" | "bad_direction" | "agg" | "muted_until">>) =>
    req(`/api/metrics/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteMetric: (id: number) => req(`/api/metrics/${id}`, { method: "DELETE" }),
  incidents: (status?: string) => req<Decision[]>(`/api/incidents?limit=200${status ? `&status=${status}` : ""}`),
  incident: (id: number) =>
    req<{ decision: Decision; points: Point[]; notifications: { kind: string; delivered: number; error: string | null; created_at: number }[]; notes: Note[] }>(
      `/api/incidents/${id}`,
    ),
  addNote: (id: number, text: string) => post<{ notes: Note[] }>(`/api/incidents/${id}/notes`, { text }),
  deleteNote: (id: number, noteId: number) => req<{ notes: Note[] }>(`/api/incidents/${id}/notes/${noteId}`, { method: "DELETE" }),
  feedback: (id: number, label: number | null) => post(`/api/incidents/${id}/feedback`, { label }),
  models: () => req<ModelsResp>("/api/models"),
  tiers: () => req<TiersResp>("/api/tiers"),
  compare: (id: number) => req<CompareResp>(`/api/metrics/${id}/compare`),
  setDefaultTier: (tier: TierId) => req<Settings>("/api/settings", { method: "PUT", body: JSON.stringify({ model_tier: tier }) }),
  setMetricTier: (id: number, tier: TierId | "default") => req(`/api/metrics/${id}`, { method: "PATCH", body: JSON.stringify({ tier }) }),
  train: () => post<TrainReport>("/api/models/train"),
  session: () => req<{ auth_required: boolean; signed_in: boolean }>("/api/session"),
  signIn: (key: string) => post<{ ok: boolean }>("/api/session", { key }),
  signOut: () => req<{ ok: boolean }>("/api/session", { method: "DELETE" }),
  billing: () => req<Billing>("/api/billing"),
  checkout: (plan: string) => post<CheckoutStart>("/api/billing/checkout", { plan }),
  verifyPayment: (body: Record<string, string>) => post<{ plan: string; status: string }>("/api/billing/verify", body),
  settings: () => req<Settings>("/api/settings"),
  saveSettings: (s: Partial<Settings>) => req<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(s) }),
  rotateKey: () => post<Settings>("/api/settings/rotate-key"),
  testSlack: () => post<{ ok: boolean; message: string }>("/api/settings/test-slack"),
  notifications: () =>
    req<{ id: number; kind: string; delivered: number; error: string | null; created_at: number; payload: { text: string } }[]>(
      "/api/notifications",
    ),
  scenarios: () => req<{ id: string; label: string; metric: string }[]>("/api/demo/scenarios"),
  inject: (scenario: string) => post<{ incident_id: number | null; metric: string }>("/api/demo/inject", { scenario }),
  resetDemo: () => post("/api/demo/reset"),
  connectors: () => req<Connector[]>("/api/connectors"),
  testConnector: (body: unknown) => post<{ ok: boolean; message: string; segments?: string[] }>("/api/connectors/test", body),
  createConnector: (body: unknown) => post<{ id: number }>("/api/connectors", body),
  runConnector: (id: number) => post<{ ok: boolean; message: string }>(`/api/connectors/${id}/run`),
  deleteConnector: (id: number) => req(`/api/connectors/${id}`, { method: "DELETE" }),
  integrations: () => req<Integration[]>("/api/integrations"),
  destinations: () => req<Destination[]>("/api/destinations"),
  testDestination: (body: unknown) => post<{ ok: boolean; message: string }>("/api/destinations/test", body),
  createDestination: (body: unknown) => post<{ id: number }>("/api/destinations", body),
  deleteDestination: (id: number) => req(`/api/destinations/${id}`, { method: "DELETE" }),
  importCsv: (form: FormData) =>
    req<{ rows: number; metrics: Record<string, { points: number; from: number; to: number }>; dimensions: string[] }>(
      "/api/import/csv",
      { method: "POST", body: form },
    ),
};

export type ModelsResp = {
  metrics: {
    metric_id: number;
    metric: string;
    kind: "base" | "custom";
    slices_trained: number;
    trained_at: number | null;
    period: string | null;
    trained_days: number | null;
    profile: number[] | null;
  }[];
  feedback: {
    active: boolean;
    weight: number;
    n_labels: number;
    positives?: number;
    negatives?: number;
    cv_accuracy?: number;
    status?: string;
    trained_at?: number;
    top_features?: { feature: string; weight: number }[];
  };
  labels: { pos: number; neg: number; unl: number };
};

export type TrainReport = {
  metrics: { metric: string; status: string; slices_trained: number; model: string | null }[];
  feedback: ModelsResp["feedback"];
};
