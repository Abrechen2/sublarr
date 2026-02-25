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
    <div className={`mt-6 first:mt-0 ${className}`}>
      {/* Section header — Sonarr-style flat separator */}
      <div
        className="flex items-center justify-between mb-0 pb-2"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div>
          <div className="flex items-center gap-2">
            {Icon && <Icon size={13} style={{ color: 'var(--text-muted)' }} />}
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              {title}
            </h3>
          </div>
          {description && (
            <p className="text-xs mt-0.5 leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              {description}
            </p>
          )}
        </div>
        {connectionStatus && (
          <ConnectionBadge status={connectionStatus} message={connectionMessage} />
        )}
      </div>
      <div className="divide-y divide-[var(--border)]">
        {children}
      </div>
    </div>
  )
}
