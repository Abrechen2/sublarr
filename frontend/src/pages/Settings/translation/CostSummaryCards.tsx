import { useTranslation } from 'react-i18next'
import { useTranslationCostSummary } from '@/hooks/useTranslationCost'

export function CostSummaryCards() {
  const { t } = useTranslation('settings')
  const { data } = useTranslationCostSummary()
  if (!data) return null

  const cards: [string, typeof data.today][] = [
    [t('translation.cost.today'), data.today],
    [t('translation.cost.last_7d'), data.last_7d],
    [t('translation.cost.last_30d'), data.last_30d],
  ]

  return (
    <div className="grid grid-cols-3 gap-3">
      {cards.map(([label, d]) => (
        <div
          key={label}
          className="rounded-lg border border-border bg-surface p-3"
        >
          <div className="text-sm text-muted">{label}</div>
          <div className="mt-1 text-xl font-semibold">
            ${d.cost_usd.toFixed(2)}
          </div>
          <div className="mt-1 text-xs text-muted">
            {d.events} {t('translation.cost.events')} · {d.cache_hits}{' '}
            {t('translation.cost.cache_hits')}
          </div>
        </div>
      ))}
    </div>
  )
}
