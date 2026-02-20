import { useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import type { ProviderHealthStats } from '@/lib/types'

interface Props {
  data: Record<string, ProviderHealthStats>
}

export function ProviderChart({ data }: Props) {
  const chartData = useMemo(() =>
    Object.entries(data).map(([name, stats]) => ({
      name,
      searches: stats.total_searches,
      downloads: stats.successful_downloads,
    })),
    [data]
  )

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-[250px] text-sm" style={{ color: 'var(--text-muted)' }}>
        No provider data yet
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" stroke="var(--text-muted)" tick={{ fontSize: 11 }} />
        <YAxis stroke="var(--text-muted)" tick={{ fontSize: 11 }} />
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
        <Bar dataKey="searches" name="Searches" fill="var(--accent)" radius={[4, 4, 0, 0]} />
        <Bar dataKey="downloads" name="Downloads" fill="var(--success)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
