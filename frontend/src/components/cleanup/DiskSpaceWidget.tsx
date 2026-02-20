/**
 * DiskSpaceWidget -- Disk usage analysis visualization for the Cleanup tab.
 *
 * Shows a pie chart of format breakdown (ASS vs SRT vs others),
 * a total vs duplicate storage bar, and a trend line of recent cleanup savings.
 */
import { useTranslation } from 'react-i18next'
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, LineChart, Line } from 'recharts'
import type { DiskSpaceStats } from '@/lib/types'
import { FORMAT_COLORS, getFormatColor, formatBytes } from '@/lib/diskUtils'

interface DiskSpaceWidgetProps {
  stats: DiskSpaceStats
}

export function DiskSpaceWidget({ stats }: DiskSpaceWidgetProps) {
  const { t } = useTranslation('settings')

  const pieData = (stats.by_format ?? []).map((f) => ({
    name: f.format.toUpperCase(),
    value: f.size_bytes,
    count: f.count,
  }))

  const barData = [
    {
      name: t('cleanup.diskSpace.totalSize', 'Total'),
      total: stats.total_size_bytes,
      duplicates: stats.duplicate_size_bytes,
    },
  ]

  const trendData = (stats.trends ?? []).slice(-30).map((tr) => ({
    date: tr.date.slice(5), // MM-DD
    freed: tr.bytes_freed,
  }))

  return (
    <div className="space-y-5">
      {/* Summary stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatBox
          label={t('cleanup.diskSpace.totalFiles', 'Total Files')}
          value={stats.total_files.toLocaleString()}
        />
        <StatBox
          label={t('cleanup.diskSpace.totalSize', 'Total Size')}
          value={formatBytes(stats.total_size_bytes)}
        />
        <StatBox
          label={t('cleanup.diskSpace.duplicates', 'Duplicates')}
          value={stats.duplicate_files.toLocaleString()}
          color="var(--warning)"
        />
        <StatBox
          label={t('cleanup.diskSpace.savings', 'Potential Savings')}
          value={formatBytes(stats.potential_savings_bytes)}
          color="var(--success)"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Format breakdown pie chart */}
        <div
          className="rounded-lg p-4"
          style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
        >
          <h4 className="text-xs font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>
            {t('cleanup.diskSpace.byFormat', 'By Format')}
          </h4>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={35}
                  outerRadius={60}
                  paddingAngle={2}
                  strokeWidth={0}
                >
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={getFormatColor(entry.name)} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number | undefined) => formatBytes(value ?? 0)}
                  contentStyle={{
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border)',
                    borderRadius: '6px',
                    fontSize: '12px',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-[160px] text-xs" style={{ color: 'var(--text-muted)' }}>
              No data
            </div>
          )}
          {/* Legend */}
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
            {pieData.map((entry) => (
              <div key={entry.name} className="flex items-center gap-1 text-[10px]">
                <div
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: getFormatColor(entry.name) }}
                />
                <span style={{ color: 'var(--text-secondary)' }}>
                  {entry.name} ({entry.count})
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Total vs duplicate storage bar */}
        <div
          className="rounded-lg p-4"
          style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
        >
          <h4 className="text-xs font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>
            {t('cleanup.diskSpace.storageBreakdown', 'Storage Breakdown')}
          </h4>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={barData} layout="vertical">
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" hide />
              <Tooltip
                formatter={(value: number | undefined, name: string | undefined) => [
                  formatBytes(value ?? 0),
                  name === 'total'
                    ? t('cleanup.diskSpace.uniqueData', 'Unique')
                    : t('cleanup.diskSpace.duplicateData', 'Duplicate'),
                ]}
                contentStyle={{
                  backgroundColor: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  borderRadius: '6px',
                  fontSize: '12px',
                }}
              />
              <Bar dataKey="total" stackId="a" fill="var(--accent)" radius={[4, 0, 0, 4]} name="total" />
              <Bar dataKey="duplicates" stackId="a" fill="var(--warning)" radius={[0, 4, 4, 0]} name="duplicates" />
            </BarChart>
          </ResponsiveContainer>
          <div className="flex gap-4 mt-2 justify-center">
            <div className="flex items-center gap-1.5 text-[10px]">
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: 'var(--accent)' }} />
              <span style={{ color: 'var(--text-secondary)' }}>{t('cleanup.diskSpace.uniqueData', 'Unique')}</span>
            </div>
            <div className="flex items-center gap-1.5 text-[10px]">
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: 'var(--warning)' }} />
              <span style={{ color: 'var(--text-secondary)' }}>{t('cleanup.diskSpace.duplicateData', 'Duplicate')}</span>
            </div>
          </div>
        </div>

        {/* Cleanup trend line */}
        <div
          className="rounded-lg p-4"
          style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
        >
          <h4 className="text-xs font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>
            {t('cleanup.diskSpace.trends', 'Cleanup Trends (30d)')}
          </h4>
          {trendData.length > 0 ? (
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={trendData}>
                <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="var(--text-muted)" />
                <YAxis tick={{ fontSize: 10 }} stroke="var(--text-muted)" tickFormatter={formatBytes} width={50} />
                <Tooltip
                  formatter={(value: number | undefined) => [formatBytes(value ?? 0), t('cleanup.diskSpace.bytesFreed', 'Freed')]}
                  contentStyle={{
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border)',
                    borderRadius: '6px',
                    fontSize: '12px',
                  }}
                />
                <Line type="monotone" dataKey="freed" stroke="var(--success)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-[160px] text-xs" style={{ color: 'var(--text-muted)' }}>
              {t('cleanup.diskSpace.noTrends', 'No cleanup history yet')}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/** Small stat summary box */
function StatBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div
      className="rounded-lg p-3 text-center"
      style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
    >
      <div
        className="text-lg font-bold tabular-nums"
        style={{ fontFamily: 'var(--font-mono)', color: color ?? 'var(--text-primary)' }}
      >
        {value}
      </div>
      <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
        {label}
      </div>
    </div>
  )
}
