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
        'flex items-center gap-4 rounded-xl p-4',
        'border border-[var(--border)] bg-[var(--bg-surface)]',
        'transition-all duration-200',
        disabled && 'opacity-40',
        className,
      )}
    >
      {/* Icon box */}
      <div
        data-testid="feature-addon-icon"
        className="flex items-center justify-center rounded-[10px] shrink-0"
        style={{
          width: 40,
          height: 40,
          backgroundColor: 'var(--accent-bg)',
        }}
      >
        <Icon size={18} style={{ color: 'var(--accent)' }} />
      </div>

      {/* Text */}
      <div className="flex flex-col gap-0.5 flex-1 min-w-0">
        <span
          data-testid="feature-addon-title"
          className="font-semibold leading-tight"
          style={{ fontSize: 14, color: 'var(--text-primary)' }}
        >
          {title}
        </span>
        <span
          data-testid="feature-addon-description"
          className="leading-snug"
          style={{ fontSize: 12, color: 'var(--text-secondary)' }}
        >
          {description}
        </span>
      </div>

      {/* Toggle */}
      <div data-testid="feature-addon-toggle" className="shrink-0">
        <Toggle checked={isEnabled} onChange={onToggle} disabled={disabled} />
      </div>
    </div>
  )
}
