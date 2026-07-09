import { useTranslation } from 'react-i18next'
import { useUsageStatsConsent } from '@/hooks/useUsageStatsConsent'

/**
 * Opt-in consent card for anonymous usage statistics. Reused in onboarding,
 * the What's-New modal (existing installs), and Settings. "No" carries equal
 * visual weight — no dark pattern.
 */
export function UsageStatsConsentCard({
  onChoice,
}: {
  onChoice?: (c: 'granted' | 'denied') => void
}) {
  const { t } = useTranslation('common')
  const { setConsent } = useUsageStatsConsent()

  const choose = (c: 'granted' | 'denied') => {
    setConsent(c)
    onChoice?.(c)
  }

  return (
    <div className="rounded-md border border-border bg-surface p-4 space-y-3">
      <h3 className="text-sm font-semibold text-primary">{t('usageStats.title')}</h3>
      <p className="text-xs text-muted">{t('usageStats.body')}</p>
      <a
        className="text-xs text-accent underline"
        href="/docs/getting-started/usage-statistics/"
        target="_blank"
        rel="noreferrer"
      >
        {t('usageStats.whatIsSent')}
      </a>
      <div className="flex gap-2 pt-1">
        <button
          data-testid="usage-stats-accept"
          className="rounded-md bg-accent px-3 py-1.5 text-xs text-white"
          onClick={() => choose('granted')}
        >
          {t('usageStats.accept')}
        </button>
        <button
          data-testid="usage-stats-decline"
          className="rounded-md border border-border px-3 py-1.5 text-xs text-muted"
          onClick={() => choose('denied')}
        >
          {t('usageStats.decline')}
        </button>
      </div>
    </div>
  )
}
