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
  const { data: providersData } = useProviders()

  const providers = providersData?.providers ?? []

  if (providers.length === 0) {
    return (
      <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>
        {t('providers.title')}...
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
              <span className="text-xs capitalize">{p.name}</span>
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
