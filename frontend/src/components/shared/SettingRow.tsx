import type { ReactNode } from 'react'
import { InfoTooltip } from './InfoTooltip'

interface SettingRowProps {
  label: string
  helpText?: string
  children: ReactNode
  className?: string
}

export function SettingRow({ label, helpText, children, className = '' }: SettingRowProps) {
  return (
    <div
      className={`grid grid-cols-1 md:grid-cols-[220px_1fr] gap-2 md:gap-4 items-start ${className}`}
    >
      <div className="flex items-center gap-1.5 pt-1">
        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          {label}
        </span>
        {helpText && <InfoTooltip text={helpText} />}
      </div>
      <div className="flex items-center min-h-[34px]">{children}</div>
    </div>
  )
}
