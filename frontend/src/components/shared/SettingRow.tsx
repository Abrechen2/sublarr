import type { ReactNode } from 'react'
import { InfoTooltip } from './InfoTooltip'
import { useAdvancedSettings } from '@/contexts/AdvancedSettingsContext'

interface SettingRowProps {
  label: string
  description?: string
  helpText?: string
  advanced?: boolean
  children: ReactNode
  className?: string
}

export function SettingRow({
  label,
  description,
  helpText,
  advanced,
  children,
  className = '',
}: SettingRowProps) {
  const { showAdvanced } = useAdvancedSettings()

  if (advanced && !showAdvanced) return null

  return (
    <div
      className={`grid grid-cols-1 md:grid-cols-[220px_1fr] gap-2 md:gap-4 items-start py-3 ${className}`}
      style={advanced ? { borderLeft: '2px solid var(--warning)', paddingLeft: '8px' } : undefined}
    >
      <div className="flex flex-col gap-0.5 pt-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            {label}
          </span>
          {helpText && <InfoTooltip text={helpText} />}
          {advanced && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded font-medium"
              style={{ backgroundColor: 'color-mix(in srgb, var(--warning) 15%, transparent)', color: 'var(--warning)' }}
            >
              Erweitert
            </span>
          )}
        </div>
        {description && (
          <span className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            {description}
          </span>
        )}
      </div>
      <div className="flex items-center min-h-[34px]">{children}</div>
    </div>
  )
}
