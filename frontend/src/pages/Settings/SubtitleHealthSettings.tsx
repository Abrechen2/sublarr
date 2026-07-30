import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getHealthReport } from '@/api/subtitleHealth'
import type { HealthReport } from '@/lib/types'
import { AIQualitySettings } from './AIQualitySettings'

export function SubtitleHealthSettings() {
  const { t } = useTranslation('library')
  const [report, setReport] = useState<HealthReport | null>(null)

  useEffect(() => {
    let alive = true
    getHealthReport()
      .then((r) => {
        if (alive) setReport(r)
      })
      .catch(() => {
        /* report is best-effort; leave null */
      })
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">{t('subtitle_health.report_title')}</h2>
      {report && (
        <p className="text-sm text-muted">
          {t('subtitle_health.report_total', {
            count: report.total_findings,
            episodes: report.affected_episodes,
          })}
        </p>
      )}
      {report && (
        <ul className="space-y-1">
          {Object.entries(report.by_type).map(([type, count]) => (
            <li key={type} className="flex justify-between text-sm">
              <span>{t(`subtitle_health.types.${type}`)}</span>
              <span className="text-muted">{count}</span>
            </li>
          ))}
        </ul>
      )}
      <AIQualitySettings />
    </div>
  )
}

export default SubtitleHealthSettings
