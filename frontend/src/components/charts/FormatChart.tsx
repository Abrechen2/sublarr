import { useMemo } from 'react'
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend,
  type PieLabelRenderProps,
} from 'recharts'

interface Props {
  data: Record<string, number>
}

const FORMAT_COLORS: Record<string, string> = {
  ass: 'var(--accent)',
  srt: 'var(--warning)',
}

const FALLBACK_COLOR = 'var(--text-muted)'

export function FormatChart({ data }: Props) {
  const chartData = useMemo(() =>
    Object.entries(data)
      .filter(([, count]) => count > 0)
      .map(([name, value]) => ({ name: name.toUpperCase(), value })),
    [data]
  )

  const total = chartData.reduce((sum, d) => sum + d.value, 0)

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-[250px] text-sm" style={{ color: 'var(--text-muted)' }}>
        No format data yet
      </div>
    )
  }

  const renderLabel = (props: PieLabelRenderProps) => {
    const name = String(props.name || '')
    const value = Number(props.value || 0)
    const pct = total > 0 ? ((value / total) * 100).toFixed(0) : '0'
    return `${name} ${pct}%`
  }

  return (
    <ResponsiveContainer width="100%" height={250}>
      <PieChart>
        <Pie
          data={chartData}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          outerRadius={80}
          label={renderLabel}
          labelLine={true}
          stroke="var(--bg-surface)"
          strokeWidth={2}
        >
          {chartData.map((entry) => (
            <Cell
              key={entry.name}
              fill={FORMAT_COLORS[entry.name.toLowerCase()] || FALLBACK_COLOR}
            />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md, 8px)',
            color: 'var(--text-primary)',
            fontSize: 12,
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  )
}
