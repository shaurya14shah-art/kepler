import {
  Area,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Decision, Point } from "../lib/api";
import { dateTime, num, time } from "../lib/format";

type Row = Point & { band: [number, number] | null };

function rows(points: Point[]): Row[] {
  return points.map((p) => ({
    ...p,
    band: p.lower != null && p.upper != null ? [p.lower, p.upper] : null,
  }));
}

export function Sparkline({ points, anomaly }: { points: Point[]; anomaly?: boolean }) {
  return (
    <div style={{ height: 64 }} aria-hidden="true">
      <ResponsiveContainer>
        <ComposedChart data={points} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <YAxis hide domain={["auto", "auto"]} />
          <Line dataKey="expected" stroke="var(--expected)" strokeDasharray="3 3" dot={false} strokeWidth={1.2} isAnimationActive={false} />
          <Line
            dataKey="value"
            stroke={anomaly ? "var(--critical)" : "var(--line)"}
            dot={false}
            strokeWidth={1.6}
            isAnimationActive={false}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function ChartTooltip({ active, payload, unit }: { active?: boolean; payload?: { payload: Row }[]; unit: string }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tt">
      <div className="muted">{dateTime(p.ts)}</div>
      <div>
        <b>{num(p.value)}</b> {unit}
      </div>
      <div className="muted">
        expected {num(p.expected)} ({num(p.band?.[0])}–{num(p.band?.[1])})
      </div>
      {p.z != null && <div className="faint">z = {p.z.toFixed(1)}</div>}
    </div>
  );
}

export function MetricChart({
  points,
  incidents = [],
  unit = "",
  height = 300,
  highlight,
}: {
  points: Point[];
  incidents?: Decision[];
  unit?: string;
  height?: number;
  highlight?: number;
}) {
  const data = rows(points);
  const spanH = data.length ? (data[data.length - 1].ts - data[0].ts) / 3600 : 0;
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="ts"
            type="number"
            domain={["dataMin", "dataMax"]}
            scale="time"
            tickFormatter={(t: number) => (spanH > 36 ? dateTime(t) : time(t))}
            tickLine={false}
            axisLine={false}
            minTickGap={40}
          />
          <YAxis tickLine={false} axisLine={false} width={48} tickFormatter={(v: number) => num(v)} />
          <Tooltip content={<ChartTooltip unit={unit} />} />
          {incidents.map((d) => (
            <ReferenceArea
              key={d.incident_id}
              x1={d.started_at - 150}
              x2={d.last_seen_at + 150}
              fill={d.incident_id === highlight ? "var(--critical)" : d.severity === "medium" ? "var(--medium)" : "var(--critical)"}
              fillOpacity={d.incident_id === highlight ? 0.22 : 0.12}
              ifOverflow="hidden"
            />
          ))}
          <Area dataKey="band" stroke="none" fill="var(--band)" isAnimationActive={false} connectNulls />
          <Line dataKey="expected" stroke="var(--expected)" strokeDasharray="4 3" dot={false} strokeWidth={1.4} isAnimationActive={false} />
          <Line dataKey="value" stroke="var(--line)" dot={false} strokeWidth={1.7} isAnimationActive={false} connectNulls />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ProfileChart({ profile }: { profile: number[] }) {
  const data = profile.map((v, i) => ({ i, v }));
  return (
    <div style={{ height: 44, width: 180 }} aria-hidden="true">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
          <YAxis hide domain={["auto", "auto"]} />
          <Area dataKey="v" stroke="var(--accent)" fill="var(--band)" strokeWidth={1.2} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
