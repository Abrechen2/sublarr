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
        'flex flex-col md:flex-row md:items-start gap-2 md:gap-6 py-3',
        'border-b border-[var(--border)] last:border-b-0',
        className,
      )}
    >
      {/* Label group — left side */}
      <div className="flex flex-col gap-0.5 pt-0.5 flex-shrink-0 md:w-[320px]">
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
        className="flex items-center min-h-[32px] md:min-w-[260px] flex-1"
      >
        {children}
      </div>
    </div>
  )
}
