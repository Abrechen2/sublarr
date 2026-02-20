/**
 * DiskSpaceWidget (Dashboard) -- Compact disk space summary widget.
 *
 * Self-contained: fetches own data via useCleanupStats.
 * Shows total subtitle files, duplicate count, potential savings, and a
 * small donut chart of format breakdown. Links to Settings Cleanup tab.
 */
import { useTranslation } from 'react-i18next'
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import { useCleanupStats } from '@/hooks/useApi'
import { HardDrive } from 'lucide-react'

const FORMAT_COLORS: Record<string, string> = {
  ass: '#14b8a6',
  srt: '#f59e0b',
  ssa: '#8b5cf6',
  sub: '#6366f1',
  vtt: '#ec4899',
}

function getFormatColor(format: string): string {
  return FORMAT_COLORS[format.toLowerCase()] ?? '#94a3b8'
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, i)
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export default function DiskSpaceDashboardWidget() {
  const { t } = useTranslation('dashboard')
  const { data: stats, isLoading } = useCleanupStats()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="skeleton w-full h-24 rounded" />
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2" style={{ color: 'var(--text-muted)' }}>
        <HardDrive size={20} />
        <span className="text-xs">{t('widgets.disk_space_no_data', 'No cleanup data')}</span>
      </div>
    )
  }

  const pieData = stats.by_format.map((f) => ({
    name: f.format.toUpperCase(),
    value: f.size_bytes,
  }))

  return (
    <div className="flex flex-col h-full">
      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="text-center">
          <div
            className="text-lg font-bold tabular-nums"
            style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}
          >
            {stats.total_files.toLocaleString()}
          </div>
          <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            {t('widgets.disk_space_files', 'Files')}
          </div>
        </div>
        <div className="text-center">
          <div
            className="text-lg font-bold tabular-nums"
            style={{ fontFamily: 'var(--font-mono)', color: 'var(--warning)' }}
          >
            {stats.duplicate_files}
          </div>
          <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            {t('widgets.disk_space_duplicates', 'Duplicates')}
          </div>
        </div>
      </div>

      {/* Donut chart */}
      {pieData.length > 0 && (
        <div className="flex-1 min-h-0">
          <ResponsiveContainer width="100%" height={100}>
            <PieChart>
              <Pie
                data={pieData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={25}
                outerRadius={40}
                paddingAngle={2}
                strokeWidth={0}
              >
                {pieData.map((entry) => (
                  <Cell key={entry.name} fill={getFormatColor(entry.name)} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Savings */}
      {stats.potential_savings_bytes > 0 && (
        <div className="text-center mt-2">
          <span className="text-xs" style={{ color: 'var(--success)' }}>
            {formatBytes(stats.potential_savings_bytes)} {t('widgets.disk_space_savings', 'savings available')}
          </span>
        </div>
      )}

      {/* Legend */}
      <div className="flex flex-wrap justify-center gap-x-2 gap-y-0.5 mt-2">
        {pieData.slice(0, 4).map((entry) => (
          <div key={entry.name} className="flex items-center gap-1 text-[9px]">
            <div
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: getFormatColor(entry.name) }}
            />
            <span style={{ color: 'var(--text-muted)' }}>{entry.name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
