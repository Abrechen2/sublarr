import React from 'react'

export function ScoreBadge({ score }: { score: number }) {
  // Match mockup: high=success, medium=accent, low=warning, very-low=error
  const color = score >= 300
    ? 'var(--success)'
    : score >= 200
      ? 'var(--accent)'
      : score >= 100
        ? 'var(--warning)'
        : 'var(--error)'
  const bg = score >= 300
    ? 'var(--success-bg)'
    : score >= 200
      ? 'var(--accent-bg)'
      : score >= 100
        ? 'var(--warning-bg)'
        : 'var(--error-bg)'
  return (
    <span
      className="inline-flex items-center tabular-nums"
      style={{
        padding: '3px 10px',
        borderRadius: '6px',
        fontSize: '12px',
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
