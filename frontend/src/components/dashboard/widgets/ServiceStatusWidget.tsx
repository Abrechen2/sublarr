/**
 * ServiceStatusWidget -- Service health status list.
 *
 * Mockup-aligned: dot + name + status text in a vertical list with borders.
 */
import { useHealth } from '@/hooks/useApi'

function formatServiceName(key: string): string {
  const name = key.includes(':') ? key.split(':').slice(1).join(':') : key
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function ServiceStatusWidget() {
  const { data: health, isLoading } = useHealth()

  if (isLoading || !health?.services) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton h-6 rounded-md" />
        ))}
      </div>
    )
  }

  const entries = Object.entries(health.services)

  return (
    <div>
      {entries.map(([name, status], i) => {
        const isNotConfigured = status === 'not configured'
        const isError = !isNotConfigured && (
          status === 'error' || status === 'fail' || status === 'failed' || status === 'disconnected'
        )
        const isOk = !isNotConfigured && !isError

        const dotColor = isOk
          ? 'var(--success)'
          : isNotConfigured
            ? 'var(--text-muted)'
            : 'var(--error)'

        const statusText = isOk
          ? (typeof status === 'string' ? status : 'Connected')
          : isNotConfigured
            ? 'Not Configured'
            : (typeof status === 'string' ? status : 'Error')

        return (
          <div
            key={name}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '9px',
              padding: '8px 0',
              borderBottom: i < entries.length - 1 ? '1px solid var(--border)' : 'none',
            }}
          >
            <div
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: dotColor,
                flexShrink: 0,
              }}
            />
            <span style={{ fontSize: '13px', fontWeight: 500, flex: 1 }}>
              {formatServiceName(name)}
            </span>
            <span
              style={{
                fontSize: '11px',
                color: isOk ? 'var(--text-secondary)' : 'var(--text-muted)',
              }}
            >
              {statusText}
            </span>
          </div>
        )
      })}
    </div>
  )
}
