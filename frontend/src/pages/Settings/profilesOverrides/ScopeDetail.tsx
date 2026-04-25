import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { InheritanceRow } from '@/components/settings/primitives'
import type { ResolvedSettings } from '@/api/profilesOverrides'
import { INHERITANCE_FIELDS, type InheritanceField } from './inheritanceFields'
import { OverrideWidget } from './OverrideWidget'

export interface ScopeDetailProps {
  readonly resolved: ResolvedSettings
  readonly onChange: (fieldKey: string, value: unknown) => void
  readonly onReset: () => void
}

export function ScopeDetail({ resolved, onChange, onReset }: ScopeDetailProps) {
  const { t } = useTranslation('settings')
  const [openOverride, setOpenOverride] = useState<string | null>(null)

  const isOverridable = resolved.scope.type === 'series' || resolved.scope.type === 'movie'

  const formatEffective = (field: InheritanceField, value: unknown): string => {
    if (value === null || value === undefined) return '—'
    if (Array.isArray(value)) return value.join(', ') || '—'
    if (typeof value === 'boolean') return value ? 'On' : 'Off'
    return String(value)
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Header strip */}
      <div className="flex items-center gap-2 pb-2 border-b border-[var(--border)]">
        <h2 className="text-sm font-semibold m-0">{resolved.scope.name}</h2>
        <span className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] px-1.5 py-0.5 rounded bg-[var(--bg-elevated)]">
          {resolved.scope.type}
        </span>
      </div>

      {/* 12 stacked InheritanceRows */}
      <div className="flex flex-col gap-2">
        {INHERITANCE_FIELDS.map((field) => {
          const setting = resolved.settings[field.key]
          if (!setting) return null
          const isOpen = openOverride === field.key
          const inheritedFromStep = setting.chain.find(
            (s) => s.scope !== resolved.scope.type && s.value !== null,
          )
          return (
            <div key={field.key}>
              <InheritanceRow
                label={t(field.labelKey, field.key)}
                source={setting.source === resolved.scope.type ? 'overridden' : 'inherited'}
                inheritedFrom={inheritedFromStep?.label}
                effective={formatEffective(field, setting.effective)}
                onOverride={isOverridable ? () => setOpenOverride(isOpen ? null : field.key) : undefined}
                overrideLabel={isOpen
                  ? t('profiles_overrides.action.close', 'Close')
                  : t('profiles_overrides.action.override', 'Override →')}
              />
              {isOpen && isOverridable && (
                <div className="ml-2 mt-1 mb-2 p-2 rounded bg-[var(--bg-primary)] border border-[var(--accent-dim)]">
                  <OverrideWidget
                    field={field}
                    value={setting.source === resolved.scope.type ? setting.effective : null}
                    onChange={(v) => onChange(field.key, v)}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Reset button */}
      {isOverridable && (
        <div className="flex justify-end pt-2 border-t border-[var(--border)]">
          <button
            type="button"
            onClick={onReset}
            className="px-2.5 py-1 text-xs rounded bg-[var(--bg-primary)] border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--error)]"
          >
            {t('profiles_overrides.action.reset_all', 'Reset all overrides')}
          </button>
        </div>
      )}
    </div>
  )
}
