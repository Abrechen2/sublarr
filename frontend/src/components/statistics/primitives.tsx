/**
 * Statistics primitives (V1.6 #9) — built per the dataviz method:
 * - single-dimension magnitude → single-hue horizontal bars (color is not
 *   identity here; the axis label is), sorted desc, with direct value labels.
 * - change-over-time, 3 measures → a multi-series line with a fixed-order,
 *   CVD-validated categorical palette + an always-present legend + tooltip.
 * - headline numbers → stat tiles (a number reads faster than a chart).
 */
import type { ReactNode } from 'react'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LabelList, ResponsiveContainer,
} from 'recharts'

// Fixed categorical order (Okabe-Ito subset), validated CVD-safe. Never cycled.
export const CATEGORICAL = ['#0072B2', '#E69F00', '#009E73', '#CC79A7', '#56B4E9', '#D55E00']

const TOOLTIP_STYLE = {
  backgroundColor: 'var(--bg-surface)',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  fontSize: 12,
  color: 'var(--text-primary)',
}

export function StatTile({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="rounded-lg p-3 bg-surface border border-border">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-xl font-semibold mt-0.5 text-primary">{value}</div>
      {sub && <div className="text-[11px] text-muted mt-0.5">{sub}</div>}
    </div>
  )
}

export function EmptyChart({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center h-[220px] text-xs" style={{ color: 'var(--text-muted)' }}>
      {label}
    </div>
  )
}

/** Horizontal single-hue bars for a {key: count} breakdown. */
export function BreakdownBars({
  data, emptyLabel, max = 8,
}: {
  data: Record<string, number>
  emptyLabel: string
  max?: number
}) {
  const rows = Object.entries(data)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, max)
  if (rows.length === 0) return <EmptyChart label={emptyLabel} />

  return (
    <ResponsiveContainer width="100%" height={Math.max(120, rows.length * 34)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 28, left: 8, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
        <XAxis type="number" stroke="var(--text-muted)" tick={{ fontSize: 11 }} allowDecimals={false} />
        <YAxis type="category" dataKey="name" stroke="var(--text-muted)" tick={{ fontSize: 11 }} width={90} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'var(--bg-surface-hover)' }} />
        <Bar dataKey="count" fill="var(--accent)" radius={[0, 4, 4, 0]} barSize={16}>
          <LabelList dataKey="count" position="right" style={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Multi-series trends line: downloads / translations / syncs over dates. */
export function TrendsChart({
  dates, series, emptyLabel,
}: {
  dates: string[]
  series: { key: string; label: string; values: number[] }[]
  emptyLabel: string
}) {
  if (dates.length === 0) return <EmptyChart label={emptyLabel} />
  const rows = dates.map((date, i) => {
    const row: Record<string, string | number> = { date: date.slice(5) } // MM-DD
    for (const s of series) row[s.key] = s.values[i] ?? 0
    return row
  })

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={rows} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="date" stroke="var(--text-muted)" tick={{ fontSize: 11 }} minTickGap={24} />
        <YAxis stroke="var(--text-muted)" tick={{ fontSize: 11 }} allowDecimals={false} width={32} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {series.map((s, i) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={CATEGORICAL[i % CATEGORICAL.length]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
