import React from 'react'
import { cn } from '@/lib/utils'

interface FormGroupProps {
  readonly label: string
  readonly hint?: string
  readonly htmlFor?: string
  readonly children: React.ReactNode
  readonly className?: string
  readonly 'data-testid'?: string
}

export function FormGroup({
  label,
  hint,
  htmlFor,
  children,
  className,
  'data-testid': testId,
}: FormGroupProps) {
  return (
    <div
      data-testid={testId ?? 'form-group'}
      className={cn(
        'flex flex-col md:flex-row md:items-start md:justify-between gap-2',
        'last:border-b-0 last:pb-0 first:pt-0',
        className,
      )}
      style={{
        padding: '12px 0',
        borderBottom: '1px solid rgba(42, 46, 56, 0.5)',
      }}
    >
      {/* Label group — left side */}
      <div className="flex flex-col gap-0.5 flex-1 min-w-0" style={{ maxWidth: '320px' }}>
        {htmlFor ? (
          <label
            htmlFor={htmlFor}
            data-testid="form-group-label"
            className="text-[13px] font-medium text-[var(--text-primary)] cursor-pointer"
          >
            {label}
          </label>
        ) : (
          <span
            data-testid="form-group-label"
            className="text-[13px] font-medium text-[var(--text-primary)]"
          >
            {label}
          </span>
        )}
        {hint && (
          <span
            data-testid="form-group-hint"
            className="text-[11px] leading-relaxed text-[var(--text-muted)]"
          >
            {hint}
          </span>
        )}
      </div>

      {/* Control group — right side */}
      <div
        data-testid="form-group-control"
        className="flex items-center gap-2"
        style={{ minWidth: '260px', justifyContent: 'flex-end' }}
      >
        {children}
      </div>
    </div>
  )
}
