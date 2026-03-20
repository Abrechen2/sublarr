import React, { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SettingsSectionProps {
  readonly title: string
  readonly description?: string
  readonly icon?: React.ReactNode
  readonly children: React.ReactNode
  readonly advanced?: React.ReactNode
  readonly className?: string
}

export function SettingsSection({
  title,
  description,
  icon,
  children,
  advanced,
  className,
}: SettingsSectionProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false)

  return (
    <div
      data-testid="settings-section"
      className={cn(
        'rounded-lg border border-[var(--border)] bg-[var(--bg-surface)]',
        className,
      )}
    >
      {/* Card header */}
      <div
        data-testid="settings-section-header"
        className="flex items-start gap-3 px-4 py-4 border-b border-[var(--border)]"
      >
        {icon && (
          <div
            data-testid="settings-section-icon"
            className="flex items-center justify-center w-8 h-8 flex-shrink-0 rounded-sm"
            style={{ backgroundColor: 'color-mix(in srgb, var(--accent) 12%, transparent)' }}
          >
            {icon}
          </div>
        )}
        <div className="flex flex-col gap-0.5 min-w-0">
          <h3
            data-testid="settings-section-title"
            className="text-[15px] font-semibold text-[var(--text-primary)] leading-tight"
          >
            {title}
          </h3>
          {description && (
            <p
              data-testid="settings-section-description"
              className="text-[12px] text-[var(--text-muted)] leading-relaxed"
            >
              {description}
            </p>
          )}
        </div>
      </div>

      {/* Content area */}
      <div data-testid="settings-section-content" className="px-4">
        {children}
      </div>

      {/* Optional advanced expandable area */}
      {advanced && (
        <div
          data-testid="settings-section-advanced"
          className="border-t border-[var(--border)]"
        >
          <button
            type="button"
            data-testid="settings-section-advanced-toggle"
            aria-expanded={advancedOpen}
            onClick={() => setAdvancedOpen((prev) => !prev)}
            className={cn(
              'flex items-center justify-between w-full px-4 py-3',
              'text-[12px] font-medium text-[var(--text-secondary)]',
              'hover:text-[var(--text-primary)] transition-colors',
            )}
          >
            <span>Advanced</span>
            <ChevronDown
              size={14}
              className={cn(
                'transition-transform duration-200',
                advancedOpen && 'rotate-180',
              )}
            />
          </button>

          {advancedOpen && (
            <div
              data-testid="settings-section-advanced-content"
              className="px-4 pb-4"
            >
              {advanced}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
