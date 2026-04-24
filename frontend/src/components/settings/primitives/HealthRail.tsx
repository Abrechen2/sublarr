import type { ReactNode } from 'react'

/**
 * HealthRail — the right-edge "what needs attention" rail for Settings pages.
 *
 * Codex blueprint #4 ("Health / Status / Checklist") calls this out as a
 * core element users rely on to debug a live install: "every important
 * broken state needs a Fix → link here, not passive hints buried in the
 * affected section."
 *
 * Render this as the `healthRail` prop of CollectionLayout / FormLayout /
 * RulesLayout. Hide the rail entirely when items.length === 0 to avoid an
 * empty visual slot.
 */

export type HealthSeverity = 'ok' | 'warn' | 'err'

export interface HealthItem {
  readonly id: string
  readonly severity: HealthSeverity
  readonly title: string
  readonly body?: ReactNode
  /** If provided, renders as a "Fix →" link at the bottom of the item. */
  readonly fix?: {
    readonly label?: string
    readonly onClick: () => void
  }
}

export interface HealthRailProps {
  readonly items: readonly HealthItem[]
  readonly title?: string
  /** Hide ok items by default; show when the user expands. Defaults to true. */
  readonly collapseOk?: boolean
}

const severityStyle: Record<HealthSeverity, { border: string; icon: string; iconCls: string }> = {
  err:  { border: 'border-[rgba(240,92,92,0.35)]',  icon: '✕', iconCls: 'text-[var(--error)]' },
  warn: { border: 'border-[rgba(232,163,61,0.35)]', icon: '!', iconCls: 'text-[var(--warning)]' },
  ok:   { border: 'border-[var(--border)]',         icon: '✓', iconCls: 'text-[var(--success)]' },
}

export function HealthRail({
  items,
  title = 'Health',
  collapseOk = true,
}: HealthRailProps) {
  const problems = items.filter((i) => i.severity !== 'ok')
  const okItems = items.filter((i) => i.severity === 'ok')
  const showOkDetail = !collapseOk
  const okCount = okItems.length

  return (
    <aside data-testid="health-rail" aria-label={title}>
      <h3 className="text-[10px] font-bold uppercase tracking-wider text-muted m-0 mb-2">
        ◉ {title}
      </h3>

      <div className="flex flex-col gap-1.5">
        {problems.map((item) => {
          const style = severityStyle[item.severity]
          return (
            <div
              key={item.id}
              data-testid="health-item"
              data-severity={item.severity}
              className={`p-2.5 rounded bg-[var(--bg-elevated)] border ${style.border}`}
            >
              <div className="flex items-start gap-2">
                <span className={`text-[11px] ${style.iconCls}`}>{style.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] font-medium">{item.title}</div>
                  {item.body && (
                    <div className="text-[10px] text-muted mt-0.5">{item.body}</div>
                  )}
                  {item.fix && (
                    <button
                      type="button"
                      onClick={item.fix.onClick}
                      data-testid="health-fix-link"
                      className="text-[10px] text-[var(--accent)] hover:text-[var(--accent-dim)] mt-1"
                    >
                      {item.fix.label ?? 'Fix →'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          )
        })}

        {showOkDetail
          ? okItems.map((item) => (
              <div
                key={item.id}
                data-testid="health-item"
                data-severity="ok"
                className="p-2.5 rounded bg-[var(--bg-elevated)] border border-[var(--border)]"
              >
                <div className="flex items-start gap-2">
                  <span className="text-[11px] text-[var(--success)]">✓</span>
                  <div className="flex-1">
                    <div className="text-[11px] font-medium">{item.title}</div>
                    {item.body && (
                      <div className="text-[10px] text-muted mt-0.5">{item.body}</div>
                    )}
                  </div>
                </div>
              </div>
            ))
          : okCount > 0 && (
              <div
                data-testid="health-ok-summary"
                className="p-2.5 rounded bg-[var(--bg-elevated)] border border-[var(--border)]"
              >
                <div className="flex items-start gap-2">
                  <span className="text-[11px] text-[var(--success)]">✓</span>
                  <div className="text-[11px]">
                    {okCount} item{okCount > 1 ? 's' : ''} healthy
                  </div>
                </div>
              </div>
            )}

        {items.length === 0 && (
          <div
            data-testid="health-empty"
            className="text-[11px] text-muted p-2"
          >
            Nothing to report.
          </div>
        )}
      </div>
    </aside>
  )
}
