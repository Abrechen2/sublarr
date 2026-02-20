import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

interface DownloadData {
  provider_name: string
  count: number
  avg_score: number
}

interface Props {
  data: DownloadData[]
}

export function DownloadChart({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[250px] text-sm" style={{ color: 'var(--text-muted)' }}>
        No download data yet
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={data} layout="vertical" margin={{ top: 5, right: 20, left: 60, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis type="number" stroke="var(--text-muted)" tick={{ fontSize: 11 }} />
        <YAxis
          type="category"
          dataKey="provider_name"
          stroke="var(--text-muted)"
          tick={{ fontSize: 11 }}
          width={55}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md, 8px)',
            color: 'var(--text-primary)',
            fontSize: 12,
          }}
          formatter={(value: unknown, _name: unknown, item: unknown) => {
            const v = Number(value || 0)
            const payload = (item as { payload?: DownloadData })?.payload
            const avgScore = payload?.avg_score?.toFixed(0) ?? '0'
            return [`${v} downloads (avg score: ${avgScore})`, 'Downloads']
          }}
        />
        <Bar dataKey="count" name="Downloads" fill="var(--accent)" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
