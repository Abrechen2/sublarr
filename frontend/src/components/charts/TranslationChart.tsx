import { useMemo } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import type { DailyStat } from '@/lib/types'

interface Props {
  data: DailyStat[]
}

export function TranslationChart({ data }: Props) {
  const chartData = useMemo(() => [...data].reverse(), [data])

  const formatDate = (date: unknown) => {
    const d = new Date(String(date))
    return `${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getDate().toString().padStart(2, '0')}`
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis
          dataKey="date"
          tickFormatter={formatDate}
          stroke="var(--text-muted)"
          tick={{ fontSize: 11 }}
        />
        <YAxis stroke="var(--text-muted)" tick={{ fontSize: 11 }} />
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md, 8px)',
            color: 'var(--text-primary)',
            fontSize: 12,
          }}
          labelFormatter={formatDate}
        />
        <Area
          type="monotone"
          dataKey="translated"
          name="Translated"
          stroke="var(--accent)"
          fill="var(--accent-subtle)"
          strokeWidth={2}
        />
        <Area
          type="monotone"
          dataKey="failed"
          name="Failed"
          stroke="var(--error)"
          fill="var(--error, rgba(239,68,68,0.1))"
          fillOpacity={0.15}
          strokeWidth={2}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
