// frontend/src/components/library/LibraryShared.tsx
export function ProgressBar({ current, total }: { current: number; total: number }) {
  const pct = total > 0 ? (current / total) * 100 : 0
  const isComplete = current === total && total > 0
  const isEmpty = total === 0
  const barColor = isEmpty
    ? 'var(--text-muted)'
    : isComplete
      ? 'var(--success)'
      : 'var(--warning)'
  return (
    <div className="flex items-center gap-2.5">
      <div
        className="flex-1 h-[18px] rounded-sm overflow-hidden relative"
        style={{ backgroundColor: 'var(--bg-primary)', minWidth: 80 }}
      >
        <div
          className="h-full rounded-sm transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: barColor }}
        />
        <span
          className="absolute inset-0 flex items-center justify-center text-[11px] font-medium"
          style={{
            color: pct > 50 ? '#fff' : 'var(--text-secondary)',
            fontFamily: 'var(--font-mono)',
            textShadow: pct > 50 ? '0 1px 2px rgba(0,0,0,0.4)' : 'none',
          }}
        >
          {current}/{total}
        </span>
      </div>
    </div>
  )
}

export function MissingBadge({ count }: { count: number }) {
  const color = count > 5 ? 'var(--error)' : count > 0 ? 'var(--warning)' : 'var(--success)'
  const bg = count > 5 ? 'var(--error-bg)' : count > 0 ? 'var(--warning-bg)' : 'var(--success-bg)'
  return (
    <span
      className="inline-flex items-center justify-center min-w-[28px] px-1.5 py-0.5 rounded text-[11px] font-bold tabular-nums"
      style={{ backgroundColor: bg, color, fontFamily: 'var(--font-mono)' }}
    >
      {count}
    </span>
  )
}
