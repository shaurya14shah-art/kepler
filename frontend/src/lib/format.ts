export function num(x: number | null | undefined, unit = ""): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "–";
  const abs = Math.abs(x);
  const s =
    abs >= 10000 ? `${(x / 1000).toFixed(1)}k` : abs >= 100 ? x.toFixed(0) : abs >= 10 ? x.toFixed(1) : x.toFixed(2).replace(/\.?0+$/, "");
  return unit && unit.length <= 3 ? `${s} ${unit}` : s;
}

export function pct(x: number | null | undefined): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "–";
  const sign = x > 0 ? "+" : "";
  return Math.abs(x) >= 1000 ? `${sign}${(x / 100).toFixed(0)}×` : `${sign}${x.toFixed(0)}%`;
}

export function time(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function dateTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
}

export function ago(ts: number, now = Date.now() / 1000): string {
  const d = Math.max(0, now - ts);
  if (d < 90) return "just now";
  if (d < 3600) return `${Math.round(d / 60)} min ago`;
  if (d < 86400) return `${Math.round(d / 3600)} h ago`;
  return `${Math.round(d / 86400)} d ago`;
}

export function duration(from: number, to: number): string {
  const m = Math.round((to - from) / 60) + 5;
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

export function whereText(where: { dimension: string; value: string }[]): string {
  const w = where.filter((x) => x.dimension !== "*");
  return w.length ? w.map((x) => `${x.dimension}=${x.value}`).join(" · ") : "all segments";
}

/** An incident's change ("▼ -42%"), or "no data since 14:05" for a metric that stopped reporting. */
export function changeText(d: { kind?: string; direction: string; change_pct: number | null; silent_since?: number | null; started_at: number }): string {
  if (d.kind === "no_data") return `no data since ${time(d.silent_since ?? d.started_at)}`;
  return `${d.direction === "spike" ? "▲" : "▼"} ${pct(d.change_pct)}`;
}
