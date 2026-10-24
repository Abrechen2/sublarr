import { useTranslation } from 'react-i18next'

/**
 * Privacy-policy link plus the named controller, shown wherever usage-stats
 * consent is asked for or changed, so the consent is informed (GDPR Art. 7,
 * Art. 13). The policy URL is a locale string, so it follows the UI language.
 */
export function UsageStatsLegalNote() {
  const { t } = useTranslation('common')

  return (
    <p className="text-xs text-muted" data-testid="usage-stats-legal-note">
      <a
        className="text-accent underline"
        href={t('usageStats.privacyUrl')}
        target="_blank"
        rel="noreferrer"
        data-testid="usage-stats-privacy-link"
      >
        {t('usageStats.privacyLink')}
      </a>
      {' · '}
      <span data-testid="usage-stats-controller">{t('usageStats.controller')}</span>
    </p>
  )
}
