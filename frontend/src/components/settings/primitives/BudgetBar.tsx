import type { ReactNode } from 'react'

/**
 * BudgetBar — live quota indicator for per-provider rate limits.
 *
 * Codex blueprint #8 explicitly called out: "Rate-Limits/Budgets: nicht nur
 * nackte Zahlen. Zeig Requests/Tag, Rest heute, letzte 24h, hard stop vs.
 * warn only." This component bundles those four facts.
 */

export interface BudgetBarProps {
  readonly label: string
  readonly used: number
  readonly total: number
  /** Optional unit after the numeric values (e.g. "requests", "tokens"). */
  readonly unit?: string
  /** Countdown/ISO timestamp for when the budget resets. */
  readonly resetsIn?: string
  /** Show a colored pill indicating whether the cap is a hard stop or warn-only. */
  readonly hardStop?: boolean
  /** Optional right-side slot for extras (e.g. learned rate-limit pill). */
  readonly extras?: ReactNode
}

function formatNumber(n: number): string {
  return n.toLocaleString('en-US')
}

export function BudgetBar({
  label,
  used,
  total,
  unit,
  resetsIn,
  hardStop = true,
  extras,
}: BudgetBarProps) {
  const safeTotal = Math.max(total, 1)
  const pctRaw = (used / safeTotal) * 100
  const pct = Math.max(0, Math.min(100, pctRaw))
  const remaining = Math.max(total - used, 0)

  let barColor = 'var(--accent)'
  if (pct >= 95) barColor = 'var(--error)'
  else if (pct >= 80) barColor = 'var(--warning)'

  return (
    <div
      data-testid="budget-bar"
      className="p-3 rounded bg-[var(--bg-elevated)] border border-[var(--border)]"
    >
      <div className="flex justify-between items-baseline mb-2">
        <span className="text-[12px] font-medium">{label}</span>
        <span className="text-[11px] text-muted">
          <strong className="text-primary">{formatNumber(used)}</strong>
          {' / '}
          {formatNumber(total)} {unit ?? ''}
        </span>
      </div>

      <div
        className="h-2 rounded bg-[var(--bg-raised)] overflow-hidden"
        role="progressbar"
        aria-label={label}
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          data-testid="budget-bar-fill"
          className="h-full rounded transition-[width] duration-300"
          style={{ width: `${pct}%`, background: barColor }}
        />
      </div>

      <div className="flex gap-4 mt-2 text-[10px] text-muted flex-wrap">
        <span>
          Remaining: <strong className="text-primary">{formatNumber(remaining)}</strong>
        </span>
        {resetsIn && (
          <span>
            Reset in: <strong className="text-primary">{resetsIn}</strong>
          </span>
        )}
        <span
          className={`px-2 py-0.5 rounded-full ${
            hardStop
              ? 'bg-[rgba(63,185,80,0.12)] text-[var(--success)]'
              : 'bg-[rgba(232,163,61,0.12)] text-[var(--warning)]'
          }`}
        >
          {hardStop ? '● hard stop' : '⚠ warn only'}
        </span>
        {extras}
      </div>
    </div>
  )
}
