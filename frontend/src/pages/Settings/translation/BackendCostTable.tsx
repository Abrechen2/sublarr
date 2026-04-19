import { useTranslation } from 'react-i18next'
import { useTranslationCostByBackend } from '@/hooks/useTranslationCost'

export function BackendCostTable() {
  const { t } = useTranslation('settings')
  const { data, isLoading } = useTranslationCostByBackend('7d')

  if (isLoading) {
    return (
      <div className="text-muted">
        {t('common.loading', { defaultValue: 'Loading...' })}
      </div>
    )
  }
  if (!data || data.backends.length === 0) {
    return (
      <div className="text-muted">{t('translation.cost.no_events_yet')}</div>
    )
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-elevated">
          <tr>
            <th className="px-3 py-2 text-left">
              {t('translation.cost.backend')}
            </th>
            <th className="px-3 py-2 text-right">
              {t('translation.cost.events')}
            </th>
            <th className="px-3 py-2 text-right">
              {t('translation.cost.cost')}
            </th>
            <th className="px-3 py-2 text-right">
              {t('translation.cost.avg_latency')}
            </th>
            <th className="px-3 py-2 text-right">
              {t('translation.cost.error_rate')}
            </th>
          </tr>
        </thead>
        <tbody>
          {data.backends.map((b) => (
            <tr key={b.backend} className="border-t border-border">
              <td className="px-3 py-2 font-mono">{b.backend}</td>
              <td className="px-3 py-2 text-right">{b.events}</td>
              <td className="px-3 py-2 text-right">
                ${b.cost_usd.toFixed(4)}
              </td>
              <td className="px-3 py-2 text-right">
                {Math.round(b.avg_latency_ms)} ms
              </td>
              <td className="px-3 py-2 text-right">
                {(b.error_rate * 100).toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
