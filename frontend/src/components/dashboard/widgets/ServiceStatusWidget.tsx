/**
 * ServiceStatusWidget -- Service health status dots grid.
 *
 * Self-contained: fetches own data via useHealth.
 * Renders colored status dots for each configured service.
 */
import { useHealth } from '@/hooks/useApi'

/** Convert raw API service key to a readable display name.
 *  e.g. "media_server:Emby" → "Emby", "media_servers" → "Media Servers" */
function formatServiceName(key: string): string {
  const name = key.includes(':') ? key.split(':').slice(1).join(':') : key
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function ServiceStatusWidget() {
  const { data: health, isLoading } = useHealth()

  if (isLoading || !health?.services) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton h-7 rounded-md" />
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {Object.entries(health.services).map(([name, status]) => {
        const isNotConfigured = status === 'not configured'
        const isError = !isNotConfigured && (
          status === 'error' || status === 'fail' || status === 'failed' || status === 'disconnected'
        )
        const isOk = !isNotConfigured && !isError
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
            <span className="text-xs truncate">{formatServiceName(name)}</span>
          </div>
        )
      })}
    </div>
  )
}
