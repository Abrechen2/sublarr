/**
 * ProviderHealthWidget -- Subtitle provider health with progress bars.
 *
 * Mockup-aligned: name | bar track | percentage
 */
import { useTranslation } from 'react-i18next'
import { useProviders } from '@/hooks/useApi'

export default function ProviderHealthWidget() {
  const { t } = useTranslation('dashboard')
  const { data: providersData, isLoading } = useProviders()

  const providers = providersData?.providers ?? []

  if (isLoading) {
    return (
      <div className="space-y-2.5">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton h-5 rounded-md" />
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {providers
        .filter((p) => p.enabled)
        .map((p) => {
          const pct = Math.round(p.stats?.success_rate ?? (p.healthy ? 100 : 0))
          return (
            <div key={p.name} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span
                style={{
                  fontSize: '13px',
                  fontWeight: 500,
                  minWidth: '85px',
                }}
              >
                {p.name}
              </span>
              <div
                style={{
                  flex: 1,
                  height: '4px',
                  background: 'rgba(255,255,255,0.05)',
                  borderRadius: '2px',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    height: '100%',
                    width: `${pct}%`,
                    borderRadius: '2px',
                    background: 'var(--accent)',
                    transition: 'width 0.3s ease',
                  }}
                />
              </div>
              <span
                style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  color: 'var(--text-secondary)',
                  minWidth: '32px',
                  textAlign: 'right' as const,
                }}
              >
                {pct}%
              </span>
            </div>
          )
        })}
    </div>
  )
}
