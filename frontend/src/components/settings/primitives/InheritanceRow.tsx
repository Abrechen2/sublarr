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

export type InheritanceSource = 'inherited' | 'overridden'

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

export function InheritanceRow({
  label,
  source,
  inheritedFrom,
  effective,
  controls,
  onOverride,
  overrideLabel = 'Override →',
}: InheritanceRowProps) {
  const isOverridden = source === 'overridden'
  const pillClass = isOverridden
    ? 'bg-[rgba(232,163,61,0.12)] text-[var(--warning)]'
    : 'bg-[rgba(29,184,212,0.10)] text-[var(--accent)]'
  const pillLabel = isOverridden ? 'overridden' : 'inherited'

  return (
    <div
      data-testid="inheritance-row"
      data-source={source}
      className="flex items-start gap-3 p-3 rounded bg-[var(--bg-elevated)] border border-[var(--border)]"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[12px] font-semibold">{label}</span>
          <span
            className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${pillClass}`}
          >
            {pillLabel}
          </span>
          {inheritedFrom && !isOverridden && (
            <span className="text-[10px] text-muted">from {inheritedFrom}</span>
          )}
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
