import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  InheritanceRow,
  type InheritanceSource,
} from '@/components/settings/primitives'
import type { ResolvedSettings, ResolvedSetting, ChainStep } from '@/api/profilesOverrides'
import { INHERITANCE_FIELDS, type InheritanceField } from './inheritanceFields'
import { OverrideWidget } from './OverrideWidget'

export interface ScopeDetailProps {
  readonly resolved: ResolvedSettings
  readonly onChange: (fieldKey: string, value: unknown) => void
  readonly onReset: () => void
}

type ScopeKind = 'global' | 'profile' | 'series' | 'movie'

/** Pick the InheritanceRow pill that honestly describes this row at this scope. */
function pillSource(scope: ScopeKind, setting: ResolvedSetting): InheritanceSource {
  const chain = setting.chain
  // Field has no chain step at this scope → truly not applicable here.
  const stepAtScope = chain.find((s) => s.scope === scope)
  if (!stepAtScope) return 'n/a'

  // At Global scope every value is the default — no override semantic exists.
  if (scope === 'global') return 'default'

  if (setting.source === scope) {
    // The effective value comes from this scope. Distinguish "set" (origin —
    // no parent had a value) from "overridden" (parent had a different value).
    const parentSteps = chain.filter((s) => s.scope !== scope)
    const overridesParent = parentSteps.some((s: ChainStep) => s.value !== null)
    return overridesParent ? 'overridden' : 'set'
  }
  return 'inherited'
}

export function ScopeDetail({ resolved, onChange, onReset }: ScopeDetailProps) {
  const { t } = useTranslation('settings')
  const [openOverride, setOpenOverride] = useState<string | null>(null)

  const scope = resolved.scope.type as ScopeKind
  const isOverridable = scope === 'series' || scope === 'movie'

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
          {scope}
        </span>
      </div>

      {/* 12 stacked InheritanceRows */}
      <div className="flex flex-col gap-2">
        {INHERITANCE_FIELDS.map((field) => {
          const setting = resolved.settings[field.key]
          if (!setting) return null
          const source = pillSource(scope, setting)
          const isOpen = openOverride === field.key
          const inheritedFromStep = setting.chain.find(
            (s) => s.scope === setting.source && s.scope !== scope,
          )
          // Don't offer override on rows that don't apply at this scope.
          const allowOverride = isOverridable && source !== 'n/a'
          return (
            <div key={field.key}>
              <InheritanceRow
                label={t(field.labelKey, field.key)}
                source={source}
                inheritedFrom={inheritedFromStep?.label}
                effective={formatEffective(field, setting.effective)}
                onOverride={allowOverride ? () => setOpenOverride(isOpen ? null : field.key) : undefined}
                overrideLabel={isOpen
                  ? t('profiles_overrides.action.close', 'Close')
                  : t('profiles_overrides.action.override', 'Override →')}
              />
              {isOpen && allowOverride && (
                <div className="ml-2 mt-1 mb-2 p-2 rounded bg-[var(--bg-primary)] border border-[var(--accent-dim)]">
                  <OverrideWidget
                    field={field}
                    value={setting.source === scope ? setting.effective : null}
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
