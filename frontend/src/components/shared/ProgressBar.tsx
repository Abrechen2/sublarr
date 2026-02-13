interface ProgressBarProps {
  value: number
  max: number
  className?: string
  showLabel?: boolean
}

export function ProgressBar({ value, max, className = '', showLabel = true }: ProgressBarProps) {
  const percent = max > 0 ? Math.round((value / max) * 100) : 0

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <div
        className="flex-1 h-1.5 rounded-full overflow-hidden"
        style={{ backgroundColor: 'var(--border)' }}
      >
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{
            width: `${percent}%`,
            background: 'linear-gradient(90deg, var(--accent-dim), var(--accent))',
            animation: percent > 0 && percent < 100 ? 'progressPulse 2s ease-in-out infinite' : undefined,
          }}
        />
      </div>
      {showLabel && (
        <span
          className="text-xs font-medium tabular-nums"
          style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', minWidth: '32px', textAlign: 'right' }}
        >
          {percent}%
        </span>
      )}
    </div>
  )
}
