"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell as BarCell,
  ErrorBar,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { brandColor } from "@/lib/brands";
import { pct } from "@/lib/format";

const axis = { fontSize: 12, fill: "var(--muted-foreground)" };
const tooltipStyle = {
  contentStyle: {
    background: "var(--popover)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    fontSize: 12,
    color: "var(--popover-foreground)",
  },
  labelStyle: { color: "var(--muted-foreground)", marginBottom: 4 },
  cursor: { fill: "var(--muted)", opacity: 0.5 },
};

type Row = Record<string, string | number | null>;

/** Grouped bars: one group per `x`, one bar per brand in `series`. Values are 0–1 rates. */
export function BrandBars({
  data,
  x,
  series,
  height = 260,
  percent = true,
  domain,
}: {
  data: Row[];
  x: string;
  series: string[];
  height?: number;
  percent?: boolean;
  domain?: [number, number];
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }} barGap={3}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey={x} tick={axis} tickLine={false} axisLine={false} />
        <YAxis
          tick={axis}
          tickLine={false}
          axisLine={false}
          domain={domain ?? (percent ? [0, 1] : [0, "auto"])}
          tickFormatter={(v) => (percent ? pct(v) : String(v))}
        />
        <Tooltip
          {...tooltipStyle}
          formatter={(v) => (percent ? pct(Number(v), 1) : Number(v).toFixed(2))}
        />
        <Legend iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12 }} itemSorter={null} />
        {series.map((s) => (
          <Bar key={s} dataKey={s} fill={brandColor(s)} radius={[3, 3, 0, 0]} maxBarSize={36} isAnimationActive={false} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TrendLines({
  data,
  series,
  height = 260,
}: {
  data: Row[];
  series: string[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="label" tick={axis} tickLine={false} axisLine={false} />
        <YAxis tick={axis} tickLine={false} axisLine={false} domain={[0, 1]} tickFormatter={(v) => pct(v)} />
        <Tooltip {...tooltipStyle} cursor={{ stroke: "var(--border)" }} formatter={(v) => pct(Number(v), 1)} />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} itemSorter={null} />
        {series.map((s) => (
          <Line
            key={s}
            type="monotone"
            dataKey={s}
            stroke={brandColor(s)}
            strokeWidth={s === "Sephora India" ? 3 : 2}
            dot={{ r: 3, strokeWidth: 0, fill: brandColor(s) }}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Horizontal bars with per-row colour, e.g. cited domains. */
export function RankBars({
  data,
  height,
}: {
  data: { name: string; value: number; color: string; hint?: string }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height ?? Math.max(160, data.length * 28 + 20)}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, left: 8, bottom: 0 }}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="name"
          width={140}
          tick={axis}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          {...tooltipStyle}
          formatter={(v, _n, item) => [`${v} citations`, (item.payload as { hint?: string }).hint ?? ""]}
        />
        <Bar dataKey="value" radius={[0, 3, 3, 0]} maxBarSize={18} isAnimationActive={false}>
          {data.map((d) => (
            <BarCell key={d.name} fill={d.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Baseline vs re-test per brand with the 95% CI of the change drawn on the re-test bar. */
export function ExperimentBars({
  data,
}: {
  data: { brand: string; baseline: number | null; retest: number | null; err: [number, number] }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="brand" tick={axis} tickLine={false} axisLine={false} />
        <YAxis tick={axis} tickLine={false} axisLine={false} domain={[0, 1]} tickFormatter={(v) => pct(v)} />
        <Tooltip {...tooltipStyle} formatter={(v) => pct(Number(v), 1)} />
        <Legend iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12 }} itemSorter={null} />
        <Bar dataKey="baseline" name="Baseline" fill="var(--chart-5)" radius={[3, 3, 0, 0]} maxBarSize={36} isAnimationActive={false} />
        <Bar dataKey="retest" name="Re-test" radius={[3, 3, 0, 0]} maxBarSize={36} isAnimationActive={false}>
          {data.map((d) => (
            <BarCell key={d.brand} fill={brandColor(d.brand)} />
          ))}
          <ErrorBar dataKey="err" width={6} stroke="var(--foreground)" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
