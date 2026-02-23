export type ConnectionStatus = 'connected' | 'error' | 'unconfigured' | 'checking'

interface ConnectionBadgeProps {
  status: ConnectionStatus
  message?: string
}

const BADGE_CONFIG = {
  connected:    { dot: '●', defaultLabel: 'Verbunden',          className: 'text-emerald-400' },
  error:        { dot: '✕', defaultLabel: 'Fehler',             className: 'text-[var(--error)]' },
  unconfigured: { dot: '○', defaultLabel: 'Nicht konfiguriert', className: 'text-[var(--text-muted)]' },
  checking:     { dot: '⟳', defaultLabel: 'Prüfe...',           className: 'text-[var(--warning)]' },
} as const

export function ConnectionBadge({ status, message }: ConnectionBadgeProps) {
  const { dot, defaultLabel, className } = BADGE_CONFIG[status]
  return (
    <span className={`flex items-center gap-1 text-xs font-medium shrink-0 ${className}`}>
      <span className={status === 'checking' ? 'animate-spin inline-block' : ''}>{dot}</span>
      <span>{message ?? defaultLabel}</span>
    </span>
  )
}
