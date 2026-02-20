import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import type { QualityTrend } from '@/lib/types'

interface Props {
  data: QualityTrend[]
  height?: number
}

export function QualityTrendChart({ data, height = 250 }: Props) {
  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm"
        style={{ color: 'var(--text-muted)', height }}
      >
        No quality data yet
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis
          dataKey="date"
          stroke="var(--text-muted)"
          tick={{ fontSize: 11 }}
          tickFormatter={(val: string) => {
            const d = new Date(val)
            return `${d.getMonth() + 1}/${d.getDate()}`
          }}
        />
        <YAxis
          yAxisId="score"
          domain={[0, 100]}
          stroke="var(--text-muted)"
          tick={{ fontSize: 11 }}
        />
        <YAxis
          yAxisId="issues"
          orientation="right"
          stroke="var(--text-muted)"
          tick={{ fontSize: 11 }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md, 8px)',
            color: 'var(--text-primary)',
            fontSize: 12,
          }}
          formatter={(value: unknown, _name: unknown) => {
            const v = Number(value || 0)
            const n = String(_name || '')
            if (n === 'Avg Score') return [`${v.toFixed(1)}/100`, n]
            return [v, n]
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line
          yAxisId="score"
          type="monotone"
          dataKey="avg_score"
          name="Avg Score"
          stroke="var(--accent)"
          strokeWidth={2}
          dot={{ r: 3 }}
        />
        <Line
          yAxisId="issues"
          type="monotone"
          dataKey="issues_count"
          name="Issues"
          stroke="var(--error)"
          strokeWidth={1.5}
          strokeDasharray="4 2"
          dot={{ r: 2 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
