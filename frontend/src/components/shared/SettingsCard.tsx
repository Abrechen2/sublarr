import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { ConnectionBadge, type ConnectionStatus } from './ConnectionBadge'

interface SettingsCardProps {
  title: string
  description?: string
  icon?: LucideIcon
  connectionStatus?: ConnectionStatus
  connectionMessage?: string
  children: ReactNode
  className?: string
}

export function SettingsCard({
  title,
  description,
  icon: Icon,
  connectionStatus,
  connectionMessage,
  children,
  className = '',
}: SettingsCardProps) {
  return (
    <div
      className={`rounded-lg border bg-[var(--bg-surface)] ${className}`}
      style={{ borderColor: 'var(--border)' }}
    >
      <div
        className="flex items-start justify-between px-5 py-4"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div>
          <div className="flex items-center gap-2">
            {Icon && <Icon size={15} style={{ color: 'var(--accent)' }} />}
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              {title}
            </h3>
          </div>
          {description && (
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {description}
            </p>
          )}
        </div>
        {connectionStatus && (
          <ConnectionBadge status={connectionStatus} message={connectionMessage} />
        )}
      </div>
      <div className="px-5 py-1 divide-y divide-[var(--border)]">
        {children}
      </div>
    </div>
  )
}
