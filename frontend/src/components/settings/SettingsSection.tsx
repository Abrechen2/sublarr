import React, { useState } from 'react'
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
        'border border-[var(--border)] bg-[var(--bg-surface)]',
        className,
      )}
      style={{ borderRadius: 'var(--radius-lg)', padding: '22px 24px', marginBottom: 0 }}
    >
      {/* Card header */}
      <div
        data-testid="settings-section-header"
        className="flex items-center gap-[10px] pb-3 mb-[18px] border-b border-[var(--border)]"
      >
        {icon && (
          <div
            data-testid="settings-section-icon"
            className="flex items-center justify-center w-8 h-8 flex-shrink-0"
            style={{ backgroundColor: 'var(--accent-bg)', borderRadius: '8px' }}
          >
            {icon}
          </div>
        )}
        <div className="flex flex-col gap-0.5 min-w-0">
          <h3
            data-testid="settings-section-title"
            className="text-[14px] font-semibold text-[var(--text-primary)] leading-tight"
          >
            {title}
          </h3>
          {description && (
            <p
              data-testid="settings-section-description"
              className="text-[11px] text-[var(--text-muted)] mt-px"
            >
              {description}
            </p>
          )}
        </div>
      </div>

      {/* Content area */}
      <div data-testid="settings-section-content">
        {children}
      </div>

      {/* Optional advanced expandable area */}
      {advanced && (
        <div data-testid="settings-section-advanced">
          <button
            type="button"
            data-testid="settings-section-advanced-toggle"
            aria-expanded={advancedOpen}
            onClick={() => setAdvancedOpen((prev) => !prev)}
            className={cn(
              'flex items-center gap-1.5 pt-[10px]',
              'text-[12px] font-medium text-[var(--text-secondary)]',
              'hover:text-[var(--accent)] transition-colors cursor-pointer select-none',
            )}
          >
            <span
              className={cn(
                'text-[10px] transition-transform duration-200 inline-block',
                advancedOpen && 'rotate-90',
              )}
            >
              &#9654;
            </span>
            <span>Advanced</span>
          </button>

          {advancedOpen && (
            <div
              data-testid="settings-section-advanced-content"
              className="pt-3 mt-[10px]"
              style={{ borderTop: '1px dashed var(--border)' }}
            >
              {advanced}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
