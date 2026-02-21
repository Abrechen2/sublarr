/**
 * ProviderHealthWidget -- Subtitle provider health status list.
 *
 * Self-contained: fetches own data via useProviders.
 * Shows provider name, colored status dot, and health text.
 */
import { useTranslation } from 'react-i18next'
import { useProviders } from '@/hooks/useApi'

export default function ProviderHealthWidget() {
  const { t } = useTranslation('dashboard')
  const { data: providersData, isLoading } = useProviders()

  const providers = providersData?.providers ?? []

  if (isLoading) {
    return (
      <div className="space-y-1.5">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton h-8 rounded-md" />
        ))}
      </div>
    )
  }

  if (providers.length === 0) {
    return (
      <div className="text-xs text-center py-4" style={{ color: 'var(--text-muted)' }}>
        {t('providers.none_configured', 'No providers configured')}
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      {providers.map((p) => {
        const statusColor = !p.enabled
          ? 'var(--text-muted)'
          : p.healthy
            ? 'var(--success)'
            : 'var(--error)'
        return (
          <div
            key={p.name}
            className="flex items-center justify-between px-2.5 py-1.5 rounded-md"
            style={{ backgroundColor: 'var(--bg-primary)' }}
          >
            <div className="flex items-center gap-2">
              <div
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ backgroundColor: statusColor }}
              />
              <span className="text-xs capitalize truncate">{p.name}</span>
            </div>
            <span
              className="text-[10px] font-medium"
              style={{ color: statusColor }}
            >
              {!p.enabled
                ? t('providers.disabled')
                : p.healthy
                  ? t('providers.healthy')
                  : t('providers.error')}
            </span>
          </div>
        )
      })}
    </div>
  )
}
