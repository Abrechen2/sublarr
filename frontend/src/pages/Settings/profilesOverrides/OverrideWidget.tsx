import { useTranslation } from 'react-i18next'
import { TriStateToggle } from '@/components/settings/primitives'
import { LanguagePillSelector } from '@/components/settings/LanguagePillSelector'
import { LANGUAGE_OPTIONS } from '@/styles/settingsShared'
import type { InheritanceField } from './inheritanceFields'

export interface OverrideWidgetProps {
  readonly field: InheritanceField
  readonly value: unknown
  readonly onChange: (value: unknown) => void
}

export function OverrideWidget({ field, value, onChange }: OverrideWidgetProps) {
  const { t } = useTranslation('settings')
  const inheritLabel = t('profiles_overrides.widget.inherit', 'Inherit')

  if (field.type === 'boolean') {
    return (
      <TriStateToggle
        value={value as boolean | null}
        onChange={(v) => onChange(v)}
        inheritLabel={inheritLabel}
        offLabel={t('profiles_overrides.widget.off', 'Off')}
        onLabel={t('profiles_overrides.widget.on', 'On')}
      />
    )
  }

  if (field.type === 'enum') {
    const v = (value ?? '') as string
    return (
      <select
        value={v}
        onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)}
        className="px-2 py-1 text-xs rounded bg-[var(--bg-primary)] border border-[var(--border)]"
      >
        <option value="">{inheritLabel}</option>
        {(field.options ?? []).map((opt) => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    )
  }

  if (field.type === 'language') {
    const v = (value ?? '') as string
    return (
      <select
        value={v}
        onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)}
        className="px-2 py-1 text-xs rounded bg-[var(--bg-primary)] border border-[var(--border)]"
      >
        <option value="">{inheritLabel}</option>
        {LANGUAGE_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    )
  }

  if (field.type === 'language_array') {
    const v = (value ?? []) as string[]
    return (
      <div className="flex items-center gap-2">
        <LanguagePillSelector
          value={v}
          options={LANGUAGE_OPTIONS}
          onChange={(next) => onChange(next.length === 0 ? null : next)}
        />
        {v.length > 0 && (
          <button
            type="button"
            onClick={() => onChange(null)}
            className="text-xs text-[var(--text-muted)] hover:text-[var(--accent)]"
          >
            {inheritLabel}
          </button>
        )}
      </div>
    )
  }

  if (field.type === 'string_array') {
    const v = (value ?? []) as string[]
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <input
          type="text"
          placeholder={t('profiles_overrides.widget.tag_input', 'comma-separated, press Enter')}
          className="px-2 py-1 text-xs rounded bg-[var(--bg-primary)] border border-[var(--border)] flex-1 min-w-[160px]"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              const target = e.target as HTMLInputElement
              const val = target.value.trim()
              if (val) {
                onChange([...v, val])
                target.value = ''
              }
            }
          }}
        />
        {v.map((tag) => (
          <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-elevated)] border border-[var(--border)]">
            {tag}
            <button
              type="button"
              onClick={() => {
                const next = v.filter((item) => item !== tag)
                onChange(next.length === 0 ? null : next)
              }}
              className="ml-1 text-[var(--text-muted)] hover:text-[var(--error)]"
            >
              ×
            </button>
          </span>
        ))}
        {v.length > 0 && (
          <button
            type="button"
            onClick={() => onChange(null)}
            className="text-xs text-[var(--text-muted)] hover:text-[var(--accent)]"
          >
            {inheritLabel}
          </button>
        )}
      </div>
    )
  }

  if (field.type === 'integer') {
    const v = value === null || value === undefined ? '' : String(value)
    return (
      <div className="flex items-center gap-2">
        <input
          type="number"
          value={v}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
          className="px-2 py-1 text-xs rounded bg-[var(--bg-primary)] border border-[var(--border)] w-24"
        />
        {value !== null && value !== undefined && (
          <button
            type="button"
            onClick={() => onChange(null)}
            className="text-xs text-[var(--text-muted)] hover:text-[var(--accent)]"
          >
            {inheritLabel}
          </button>
        )}
      </div>
    )
  }

  // string fallback
  const sv = (value ?? '') as string
  return (
    <input
      type="text"
      value={sv}
      onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)}
      className="px-2 py-1 text-xs rounded bg-[var(--bg-primary)] border border-[var(--border)] w-40"
    />
  )
}
