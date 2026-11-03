import { useTranslation } from 'react-i18next'

export type ConnectionStatus = 'connected' | 'error' | 'unconfigured' | 'checking'

interface ConnectionBadgeProps {
  status: ConnectionStatus
  message?: string
}

const BADGE_CONFIG = {
  connected:    { dot: '●', labelKey: 'connection_badge.connected',    className: 'text-emerald-400' },
  error:        { dot: '✕', labelKey: 'connection_badge.error',        className: 'text-[var(--error)]' },
  unconfigured: { dot: '○', labelKey: 'connection_badge.unconfigured', className: 'text-[var(--text-muted)]' },
  checking:     { dot: '⟳', labelKey: 'connection_badge.checking',     className: 'text-[var(--warning)]' },
} as const

export function ConnectionBadge({ status, message }: ConnectionBadgeProps) {
  const { t } = useTranslation('common')
  const { dot, labelKey, className } = BADGE_CONFIG[status]
  return (
    <span className={`flex items-center gap-1 text-xs font-medium shrink-0 ${className}`}>
      <span className={status === 'checking' ? 'motion-safe:animate-spin inline-block' : ''}>{dot}</span>
      <span>{message ?? t(labelKey)}</span>
    </span>
  )
}
