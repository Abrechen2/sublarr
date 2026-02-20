/**
 * TranslationStatsWidget -- Total Stats, By Format, and System panels.
 *
 * Self-contained: fetches own data via useStats.
 * Includes live uptime counter with interval-based tick.
 * Three columns on wide layouts, stacked on narrow.
 */
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useStats } from '@/hooks/useApi'
import { formatDuration } from '@/lib/utils'

export default function TranslationStatsWidget() {
  const { t } = useTranslation('dashboard')
  const { data: stats } = useStats()

  // Live Uptime Counter
  const [currentUptime, setCurrentUptime] = useState<number | null>(null)
  const initialUptimeRef = useRef<number | null>(null)
  const lastUpdateTimeRef = useRef<number | null>(null)

  useEffect(() => {
    if (stats?.uptime_seconds !== undefined) {
      if (initialUptimeRef.current !== stats.uptime_seconds) {
        initialUptimeRef.current = stats.uptime_seconds
        lastUpdateTimeRef.current = Date.now()
        setCurrentUptime(stats.uptime_seconds)
      }
    }
  }, [stats?.uptime_seconds])

  useEffect(() => {
    if (
      initialUptimeRef.current === null ||
      lastUpdateTimeRef.current === null
    ) {
      return
    }

    const interval = setInterval(() => {
      const now = Date.now()
      const elapsed = (now - lastUpdateTimeRef.current!) / 1000
      setCurrentUptime(initialUptimeRef.current! + elapsed)
    }, 1000)

    return () => clearInterval(interval)
  }, [])

  if (!stats) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="skeleton w-full h-24 rounded" />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 h-full">
      {/* Total Stats */}
      <div>
        <div
          className="text-xs font-semibold mb-2 uppercase tracking-wider"
          style={{ color: 'var(--text-muted)' }}
        >
          {t('total_stats.title')}
        </div>
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>{t('total_stats.translated')}</span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                color: 'var(--success)',
              }}
            >
              {stats.total_translated}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span>{t('total_stats.failed')}</span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                color: 'var(--error)',
              }}
            >
              {stats.total_failed}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span>{t('total_stats.skipped')}</span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-secondary)',
              }}
            >
              {stats.total_skipped}
            </span>
          </div>
        </div>
      </div>

      {/* By Format */}
      <div>
        <div
          className="text-xs font-semibold mb-2 uppercase tracking-wider"
          style={{ color: 'var(--text-muted)' }}
        >
          {t('by_format.title')}
        </div>
        <div className="space-y-2">
          {Object.entries(stats.by_format || {}).map(([fmt, count]) => (
            <div key={fmt} className="flex justify-between text-sm">
              <span className="uppercase">{fmt}</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{count}</span>
            </div>
          ))}
          {Object.keys(stats.by_format || {}).length === 0 && (
            <div
              className="text-sm"
              style={{ color: 'var(--text-secondary)' }}
            >
              {t('by_format.no_data')}
            </div>
          )}
        </div>
      </div>

      {/* System */}
      <div>
        <div
          className="text-xs font-semibold mb-2 uppercase tracking-wider"
          style={{ color: 'var(--text-muted)' }}
        >
          {t('system.title')}
        </div>
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>{t('system.uptime')}</span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>
              {currentUptime !== null
                ? formatDuration(currentUptime)
                : stats?.uptime_seconds !== undefined
                  ? formatDuration(stats.uptime_seconds)
                  : '\u2014'}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span>{t('system.batch_running')}</span>
            <span>
              {stats.batch_running ? t('system.yes') : '\u2014'}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span>{t('system.quality_warnings')}</span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                color:
                  stats.quality_warnings > 0
                    ? 'var(--warning)'
                    : 'inherit',
              }}
            >
              {stats.quality_warnings}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
