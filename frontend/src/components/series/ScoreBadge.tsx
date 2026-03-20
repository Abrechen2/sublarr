import React from 'react'

interface ScoreBadgeProps {
  readonly score: number
  readonly size?: 'sm' | 'md'
}

/**
 * Score badge with mockup-matched color tiers:
 *   ≥80 = success (green), 50–79 = accent (teal), 1–49 = warning (amber), 0 = error (red)
 */
export function ScoreBadge({ score, size = 'md' }: ScoreBadgeProps) {
  const color = score >= 70
    ? 'var(--success)'
    : score >= 50
      ? 'var(--accent)'
      : score >= 1
        ? 'var(--warning)'
        : 'var(--error)'
  const bg = score >= 70
    ? 'var(--success-bg)'
    : score >= 50
      ? 'var(--accent-bg)'
      : score >= 1
        ? 'var(--warning-bg)'
        : 'var(--error-bg)'

  const padding = size === 'sm' ? '2px 8px' : '3px 10px'
  const fontSize = size === 'sm' ? '11px' : '12px'

  return (
    <span
      data-testid="score-badge"
      className="inline-flex items-center tabular-nums"
      style={{
        padding,
        borderRadius: '6px',
        fontSize,
        fontWeight: 700,
        backgroundColor: bg,
        color,
        fontFamily: 'var(--font-mono)',
        textAlign: 'center',
        width: 'fit-content',
      }}
    >
      {score}
    </span>
  )
}
