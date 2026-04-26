import { useState } from 'react'
import { Link } from 'react-router-dom'
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
  /** When defined, shows a destructive "Remove from overrides" button at footer. */
  readonly onRemove?: () => void
  /** When defined, shows a back-link at the top of the detail pane. */
  readonly backHref?: string
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

export function ScopeDetail({ resolved, onChange, onReset, onRemove, backHref }: ScopeDetailProps) {
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

  const handleRemove = () => {
    const confirmed = window.confirm(
      t(
        'profiles_overrides.action.remove_overrides_confirm',
        'Remove all overrides for this series/movie? It will disappear from the tree.',
      ),
    )
    if (confirmed) onRemove?.()
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Back link — shown when navigated from series/movie detail page */}
      {backHref && (
        <div className="pb-1">
          <Link
            to={backHref}
            data-testid="scope-detail-back-link"
            className="text-xs text-[var(--accent)] hover:underline flex items-center gap-1"
          >
            {t('profiles_overrides.action.back_to', '← Back to')} {resolved.scope.name}
          </Link>
        </div>
      )}

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

      {/* Footer actions — Reset + Remove */}
      {isOverridable && (
        <div className="flex items-center justify-between pt-2 border-t border-[var(--border)]">
          {/* Remove override row — destructive, distinct from Reset */}
          {onRemove ? (
            <button
              type="button"
              onClick={handleRemove}
              data-testid="scope-detail-remove-btn"
              className="px-2.5 py-1 text-xs rounded bg-[var(--bg-primary)] border border-[var(--error)] text-[var(--error)] hover:bg-[var(--error)] hover:text-white"
            >
              {t('profiles_overrides.action.remove_overrides', 'Remove from overrides')}
            </button>
          ) : (
            <span />
          )}

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
