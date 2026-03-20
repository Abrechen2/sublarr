import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Toggle } from '@/components/shared/Toggle'

interface FeatureAddonProps {
  readonly icon: LucideIcon
  readonly title: string
  readonly description: string
  readonly isEnabled: boolean
  readonly onToggle: (enabled: boolean) => void
  readonly disabled?: boolean
  readonly className?: string
}

export function FeatureAddon({
  icon: Icon,
  title,
  description,
  isEnabled,
  onToggle,
  disabled = false,
  className,
}: FeatureAddonProps) {
  return (
    <div
      data-testid="feature-addon"
      className={cn(
        'flex items-center border bg-[var(--bg-surface)]',
        'transition-all duration-200',
        isEnabled && 'border-[rgba(29,184,212,0.3)]',
        !isEnabled && 'border-[var(--border)]',
        disabled && 'opacity-40',
        className,
      )}
      style={{
        borderRadius: 'var(--radius-lg)',
        padding: '18px 24px',
        gap: '14px',
      }}
    >
      {/* Icon box — uses upgrade-bg per mockup */}
      <div
        data-testid="feature-addon-icon"
        className="flex items-center justify-center shrink-0"
        style={{
          width: 40,
          height: 40,
          borderRadius: 10,
          backgroundColor: 'var(--upgrade-bg)',
        }}
      >
        <Icon size={18} style={{ color: 'var(--upgrade)' }} />
      </div>

      {/* Text */}
      <div className="flex flex-col gap-0.5 flex-1 min-w-0">
        <span
          data-testid="feature-addon-title"
          className="leading-tight"
          style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}
        >
          {title}
        </span>
        <span
          data-testid="feature-addon-description"
          style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.4 }}
        >
          {description}
        </span>
      </div>

      {/* Status: badge + toggle */}
      <div data-testid="feature-addon-status" className="flex items-center gap-2 shrink-0">
        <span
          data-testid="feature-addon-badge"
          className="font-semibold"
          style={{
            fontSize: 10,
            padding: '3px 9px',
            borderRadius: 999,
            backgroundColor: isEnabled ? 'var(--success-bg)' : 'var(--bg-elevated)',
            color: isEnabled ? 'var(--success)' : 'var(--text-muted)',
          }}
        >
          {isEnabled ? 'Enabled' : 'Disabled'}
        </span>
        <Toggle checked={isEnabled} onChange={onToggle} disabled={disabled} />
      </div>
    </div>
  )
}
