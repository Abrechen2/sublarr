// Compact 7d health-bar visualisation: total stats split into colour
// proportions. Designed to read at a glance — no axis, no labels — so
// the user can scan a row and immediately see "lots of green" vs
// "mostly red".

import { useTranslation } from 'react-i18next'

interface SchedulerJobStats7d {
  readonly ok: number
  readonly error: number
  readonly timeout: number
  readonly missed: number
  readonly skipped_overlap?: number
}

export function HealthBar({ stats }: { stats: SchedulerJobStats7d }) {
  const { t } = useTranslation('settings')
  const skipped = stats.skipped_overlap ?? 0
  const total = stats.ok + stats.error + stats.timeout + stats.missed + skipped
  if (total === 0) {
    return (
      <div
        className="h-1 w-full overflow-hidden rounded-full"
        style={{ backgroundColor: 'var(--bg-elevated)' }}
        aria-label={t('health_bar.no_runs')}
      />
    )
  }
  const segments = [
    { count: stats.ok, color: 'var(--success)' },
    { count: stats.error, color: 'var(--error)' },
    { count: stats.timeout, color: 'var(--warning)' },
    { count: stats.missed, color: 'var(--warning)' },
    { count: skipped, color: 'var(--text-muted)' },
  ].filter((s) => s.count > 0)

  return (
    <div
      className="flex h-1 w-full overflow-hidden rounded-full"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      role="img"
      aria-label={t('health_bar.aria_summary', {
        ok: stats.ok,
        error: stats.error,
        timeout: stats.timeout,
        missed: stats.missed,
      })}
    >
      {segments.map((s, i) => (
        <div
          key={i}
          style={{
            width: `${(s.count / total) * 100}%`,
            backgroundColor: s.color,
          }}
        />
      ))}
    </div>
  )
}
