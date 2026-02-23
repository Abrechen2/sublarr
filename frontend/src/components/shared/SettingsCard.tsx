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
      className={`rounded-lg overflow-hidden ${className}`}
      style={{
        border: '1px solid var(--border-hover)',
        backgroundColor: 'var(--bg-elevated)',
        boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
      }}
    >
      <div
        className="flex items-start justify-between px-5 py-3.5"
        style={{
          backgroundColor: 'var(--bg-surface-hover)',
          borderBottom: '2px solid var(--border-hover)',
          borderLeft: '3px solid var(--accent)',
        }}
      >
        <div>
          <div className="flex items-center gap-2">
            {Icon && <Icon size={14} style={{ color: 'var(--accent)' }} />}
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              {title}
            </h3>
          </div>
          {description && (
            <p className="text-xs mt-0.5 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              {description}
            </p>
          )}
        </div>
        {connectionStatus && (
          <ConnectionBadge status={connectionStatus} message={connectionMessage} />
        )}
      </div>
      <div className="px-5 divide-y divide-[var(--border)]">
        {children}
      </div>
    </div>
  )
}
