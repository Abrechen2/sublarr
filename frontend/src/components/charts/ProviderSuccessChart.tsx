import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'

interface ProviderSuccessData {
  provider: string
  success: number
  failed: number
}

interface Props {
  data: ProviderSuccessData[]
  height?: number
}

export function ProviderSuccessChart({ data, height = 250 }: Props) {
  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm"
        style={{ color: 'var(--text-muted)', height }}
      >
        No provider data yet
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="provider" stroke="var(--text-muted)" tick={{ fontSize: 11 }} />
        <YAxis stroke="var(--text-muted)" tick={{ fontSize: 11 }} />
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
            const n = String(_name || '')
            const payload = (item as { payload?: ProviderSuccessData })?.payload
            if (payload) {
              const total = payload.success + payload.failed
              const rate = total > 0 ? ((payload.success / total) * 100).toFixed(1) : '0'
              if (n === 'Success') return [`${v} (${rate}% success rate)`, n]
            }
            return [v, n]
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="success" name="Success" stackId="a" fill="var(--success)" radius={[0, 0, 0, 0]} />
        <Bar dataKey="failed" name="Failed" stackId="a" fill="var(--error)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
