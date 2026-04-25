/**
 * TriStateToggle — three-state inherit/false/true control.
 *
 * Shared primitive for boolean override widgets that need an explicit
 * "inherit from parent scope" state. Extracted from the
 * SeriesSettingsPanel cleanup_foreign_tracks pattern (0.71.1) so the
 * Profiles & Overrides page and any future inheritance UX can reuse it.
 *
 * value === null  → Inherit selected
 * value === false → Off selected
 * value === true  → On selected
 */
export interface TriStateToggleProps {
  readonly value: boolean | null
  readonly onChange: (value: boolean | null) => void
  readonly inheritLabel?: string
  readonly offLabel?: string
  readonly onLabel?: string
}

export function TriStateToggle({
  value,
  onChange,
  inheritLabel = 'Inherit',
  offLabel = 'Off',
  onLabel = 'On',
}: TriStateToggleProps) {
  const states: { v: boolean | null; label: string }[] = [
    { v: null, label: inheritLabel },
    { v: false, label: offLabel },
    { v: true, label: onLabel },
  ]
  return (
    <div data-testid="tri-state-toggle" className="inline-flex gap-1">
      {states.map((s) => {
        const active = value === s.v
        return (
          <button
            key={String(s.v)}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(s.v)}
            className={
              active
                ? 'px-2.5 py-1 text-xs font-medium rounded bg-[var(--accent-bg)] text-[var(--accent)] border border-[var(--accent-dim)]'
                : 'px-2.5 py-1 text-xs font-medium rounded bg-[var(--bg-primary)] text-[var(--text-muted)] border border-[var(--border)] hover:opacity-80'
            }
          >
            {s.label}
          </button>
        )
      })}
    </div>
  )
}
