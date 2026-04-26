import type { ReactNode } from 'react'

/**
 * InheritanceRow — a single resolved setting with its inheritance chain.
 *
 * Shared primitive used inside RulesLayout detail panes and anywhere
 * else we need to show "inherited from X / overridden here / effective: Y".
 *
 * Matches the contract of the 0.71.1 backend fields:
 *   cleanup_foreign_tracks_override:  null | true | false (raw column)
 *   cleanup_foreign_tracks_effective: bool                 (resolved)
 */

/**
 * Pill semantics:
 *   - 'default'    — value is the global / starting default at this scope.
 *                    Used at Global scope for everything, and at any scope
 *                    when no parent had a value to override.
 *   - 'set'        — this scope is the origin of the value (no parent had
 *                    one to override). Used at Profile scope for fields
 *                    that exist only at profile level.
 *   - 'inherited'  — value comes from a parent scope (chain step above).
 *   - 'overridden' — this scope replaces a non-null value from a parent.
 *   - 'n/a'        — field does not apply at this scope (e.g. series-only
 *                    field viewed at Profile scope).
 */
export type InheritanceSource = 'default' | 'set' | 'inherited' | 'overridden' | 'n/a'

export interface InheritanceRowProps {
  readonly label: string
  readonly source: InheritanceSource
  /** Human-readable parent scope when source === 'inherited' (e.g. "Global default"). */
  readonly inheritedFrom?: string
  /** The resolved/effective value, already formatted for display (e.g. "Always strip"). */
  readonly effective: ReactNode
  /** Optional slot below the effective value — e.g. an <OverrideWidget> or a link. */
  readonly controls?: ReactNode
  /** Optional click handler rendered as a compact link on the right. */
  readonly onOverride?: () => void
  readonly overrideLabel?: string
}

interface PillStyle {
  readonly cls: string
  readonly label: string
}

const PILL_STYLES: Record<InheritanceSource, PillStyle> = {
  overridden: {
    cls: 'bg-[rgba(232,163,61,0.12)] text-[var(--warning)]',
    label: 'overridden',
  },
  inherited: {
    cls: 'bg-[rgba(29,184,212,0.10)] text-[var(--accent)]',
    label: 'inherited',
  },
  set: {
    cls: 'bg-[rgba(29,184,212,0.10)] text-[var(--accent)]',
    label: 'set here',
  },
  default: {
    cls: 'bg-[var(--bg-primary)] text-[var(--text-muted)] border border-[var(--border)]',
    label: 'default',
  },
  'n/a': {
    cls: 'bg-[var(--bg-primary)] text-[var(--text-muted)] border border-[var(--border)]',
    label: 'n/a',
  },
}

export function InheritanceRow({
  label,
  source,
  inheritedFrom,
  effective,
  controls,
  onOverride,
  overrideLabel = 'Override →',
}: InheritanceRowProps) {
  const pill = PILL_STYLES[source]
  const isMuted = source === 'n/a'
  const showFrom = inheritedFrom && source === 'inherited'

  return (
    <div
      data-testid="inheritance-row"
      data-source={source}
      className={`flex items-start gap-3 p-3 rounded bg-[var(--bg-elevated)] border border-[var(--border)] ${
        isMuted ? 'opacity-60' : ''
      }`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[12px] font-semibold">{label}</span>
          <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${pill.cls}`}>
            {pill.label}
          </span>
          {showFrom && <span className="text-[10px] text-muted">from {inheritedFrom}</span>}
        </div>
        <div className="text-[12px] text-primary">
          effective: <strong>{effective}</strong>
        </div>
        {controls && <div className="mt-2">{controls}</div>}
      </div>

      {onOverride && (
        <button
          type="button"
          onClick={onOverride}
          data-testid="inheritance-override-btn"
          className="text-[11px] text-[var(--accent)] hover:text-[var(--accent-dim)] flex-shrink-0"
        >
          {overrideLabel}
        </button>
      )}
    </div>
  )
}
