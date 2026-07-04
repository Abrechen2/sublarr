import type { TranslationBackendInfo } from '@/lib/types'

interface BackendSelectProps {
  value: string
  onChange: (name: string) => void
  backends: TranslationBackendInfo[]
  inheritLabel?: string
  noneLabel?: string
  unconfiguredLabel?: string
  'data-testid'?: string
}

export function BackendSelect({
  value,
  onChange,
  backends,
  inheritLabel,
  noneLabel,
  unconfiguredLabel,
  'data-testid': testId,
}: BackendSelectProps) {
  const emptyLabel = inheritLabel ?? noneLabel
  return (
    <select
      data-testid={testId}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full px-2.5 py-1.5 rounded text-xs bg-surface border border-border text-primary"
    >
      {emptyLabel !== undefined && <option value="">{emptyLabel}</option>}
      {backends.map((b) => {
        const flag =
          b.configured || b.name === 'ollama' || !unconfiguredLabel ? '' : ` (${unconfiguredLabel})`
        return (
          <option key={b.name} value={b.name}>
            {b.display_name}
            {flag}
          </option>
        )
      })}
    </select>
  )
}
