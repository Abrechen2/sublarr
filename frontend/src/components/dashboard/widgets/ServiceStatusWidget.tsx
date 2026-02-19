/**
 * ServiceStatusWidget -- Service health status dots grid.
 *
 * Self-contained: fetches own data via useHealth.
 * Renders colored status dots for each configured service.
 */
import { useTranslation } from 'react-i18next'
import { useHealth } from '@/hooks/useApi'

export default function ServiceStatusWidget() {
  const { t } = useTranslation('dashboard')
  const { data: health } = useHealth()

  if (!health?.services) {
    return (
      <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>
        {t('services.title')}...
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {Object.entries(health.services).map(([name, status]) => {
        const isOk =
          status === 'OK' || (typeof status === 'string' && status.startsWith('OK'))
        const isNotConfigured = status === 'not configured'
        return (
          <div
            key={name}
            className="flex items-center gap-2 px-2.5 py-1.5 rounded-md"
            style={{ backgroundColor: 'var(--bg-primary)' }}
          >
            <div
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{
                backgroundColor: isOk
                  ? 'var(--success)'
                  : isNotConfigured
                    ? 'var(--text-muted)'
                    : 'var(--error)',
              }}
            />
            <span className="text-xs capitalize truncate">{name}</span>
          </div>
        )
      })}
    </div>
  )
}
