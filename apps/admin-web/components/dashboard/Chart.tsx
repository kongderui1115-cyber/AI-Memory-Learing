"use client";

import { useId } from "react";
import type { CSSProperties } from "react";
import { Area, Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import styles from "./chart.module.css";

export interface ChartPoint {
  date: string;
  [key: string]: string | number | null;
}

export interface ChartSeries {
  key: string;
  label: string;
  color: string;
  kind: "line" | "bar" | "area";
  axis?: "count" | "percent";
  dashed?: boolean;
  unit?: string;
}

type TooltipEntry = {
  dataKey?: unknown;
  value?: unknown;
  payload?: ChartPoint;
};

function ChartTooltip({
  active,
  label,
  payload,
  series,
  noteForPoint,
}: {
  active?: boolean;
  label?: unknown;
  payload?: ReadonlyArray<TooltipEntry>;
  series: ChartSeries[];
  noteForPoint?: (point: ChartPoint) => string | undefined;
}) {
  if (!active || !payload?.length) return null;
  const firstPoint = payload[0]?.payload;
  const note = firstPoint ? noteForPoint?.(firstPoint) : undefined;
  return (
    <div className={styles.tooltip}>
      <strong>{String(label ?? "")}</strong>
      {series.map(item => {
        const match = payload.find(entry => entry.dataKey === item.key);
        if (!match || typeof match.value !== "number") return null;
        return (
          <div key={item.key}>
            <span><i style={{ background: item.color }} />{item.label}</span>
            <b>{match.value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}{item.unit ?? (item.axis === "percent" ? "%" : "")}</b>
          </div>
        );
      })}
      {note && <small>{note}</small>}
    </div>
  );
}

const compactNumber = new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 });

export default function TrendChart({
  data,
  series,
  label,
  height = 244,
  countUnit,
  percentAxis,
  noteForPoint,
}: {
  data: ChartPoint[];
  series: ChartSeries[];
  label: string;
  height?: number;
  countUnit?: string;
  percentAxis?: boolean;
  noteForPoint?: (point: ChartPoint) => string | undefined;
}) {
  const prefix = useId().replace(/[^a-z0-9_-]/gi, "");
  const percent = percentAxis ?? series.some(item => item.axis === "percent");
  const count = series.some(item => item.axis !== "percent");
  if (!data.length) return <div className={styles.empty} style={{ minHeight: height }}>暂无数据</div>;
  return (
    <div className={styles.container} role="group" aria-label={label}>
      <div className={styles.legend}>
        {series.map(item => <span key={item.key}>
          <i className={item.dashed ? styles.dashed : ""} style={{ "--series-color": item.color } as CSSProperties} />
          {item.label}
        </span>)}
      </div>
      <div className={styles.axisLabels}>
        <span>{count ? countUnit : "百分比 · %"}</span>
        {count && percent && <span>百分比 · %</span>}
      </div>
      <div className={styles.plot} style={{ height }}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <ComposedChart data={data} margin={{ top: 6, right: count && percent ? 4 : 10, left: 0, bottom: 3 }} barGap={4} accessibilityLayer>
            <defs>
              {series.map((item, index) => (
                <linearGradient key={item.key} id={`${prefix}-${index}`} x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor={item.color} stopOpacity={item.kind === "bar" ? 0.95 : 0.32} />
                  <stop offset="100%" stopColor={item.color} stopOpacity={item.kind === "bar" ? 0.39 : 0.015} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid stroke="var(--border, #243353)" strokeDasharray="3 5" vertical={false} opacity={0.72} />
            <XAxis dataKey="date" tickFormatter={value => /^\d{4}-\d{2}-\d{2}$/.test(String(value)) ? String(value).slice(5).replace("-", "/") : String(value)} axisLine={false} tickLine={false} minTickGap={18} tickMargin={11} tick={{ fontSize: 11, fill: "var(--muted, #a5b4cf)" }} />
            {count && <YAxis yAxisId="count" width={43} axisLine={false} tickLine={false} tickCount={5} tickFormatter={value => compactNumber.format(value)} tick={{ fontSize: 11, fill: "var(--muted, #a5b4cf)" }} />}
            {percent && <YAxis yAxisId="percent" width={44} orientation={count ? "right" : "left"} domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={value => `${value}%`} axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "var(--muted, #a5b4cf)" }} />}
            <Tooltip cursor={{ fill: "#9baeff", fillOpacity: 0.045, stroke: "#acbfff", strokeOpacity: 0.18 }} content={<ChartTooltip series={series} noteForPoint={noteForPoint} />} />
            {series.map((item, index) => {
              const gradient = `url(#${prefix}-${index})`;
              if (item.kind === "bar") return <Bar key={item.key} dataKey={item.key} name={item.label} yAxisId={item.axis ?? "count"} fill={gradient} maxBarSize={19} radius={[4, 4, 0, 0]} isAnimationActive={false} />;
              if (item.kind === "area") return <Area key={item.key} dataKey={item.key} name={item.label} yAxisId={item.axis ?? "count"} type="monotone" fill={gradient} stroke={item.color} strokeWidth={2.35} dot={data.length <= 10 ? { r: 3.2, strokeWidth: 2, fill: "var(--surface, #101a30)" } : false} isAnimationActive={false} />;
              return <Line key={item.key} dataKey={item.key} name={item.label} yAxisId={item.axis ?? "count"} type="monotone" stroke={item.color} strokeWidth={2.3} strokeDasharray={item.dashed ? "6 5" : undefined} dot={data.length <= 10 ? { r: 3.2, strokeWidth: 2, fill: "var(--surface, #101a30)" } : false} activeDot={{ r: 5, fill: item.color, stroke: "var(--surface, #101a30)", strokeWidth: 2 }} isAnimationActive={false} connectNulls={false} />;
            })}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export { TrendChart };

export function RingChart({
  value,
  label,
  color = "var(--cyan, #3bd9eb)",
  size = 104,
}: {
  value: number;
  label: string;
  color?: string;
  size?: number;
}) {
  const bounded = Math.max(0, Math.min(100, value));
  return (
    <div
      className={styles.ring}
      style={{ "--ring-value": `${bounded}%`, "--ring-color": color, "--ring-size": `${size}px` } as CSSProperties}
      role="img"
      aria-label={`${label} ${bounded}%`}
    >
      <div>
        <strong>{bounded.toLocaleString("zh-CN", { maximumFractionDigits: 1 })}<span>%</span></strong>
        <small>{label}</small>
      </div>
    </div>
  );
}
