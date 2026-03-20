import type React from 'react'

/** CSS grid template matching the mockup exactly */
export const EPISODE_GRID_COLUMNS = '50px 1fr 80px 90px 70px 140px'

/** Episode header row — column labels */
export function EpisodeGridHeader() {
  return (
    <div
      data-testid="episode-grid-header"
      style={{
        display: 'grid',
        gridTemplateColumns: EPISODE_GRID_COLUMNS,
        padding: '6px 14px',
        fontSize: '10px',
        fontWeight: 600,
        color: 'var(--text-muted)',
        textTransform: 'uppercase' as const,
        letterSpacing: '0.5px',
        gap: '10px',
      }}
    >
      <span>#</span>
      <span>Episode</span>
      <span>Format</span>
      <span>Provider</span>
      <span>Score</span>
      <span style={{ textAlign: 'right' }}>Actions</span>
    </div>
  )
}

interface EpisodeGridRowStyleProps {
  readonly status: 'ok' | 'missing' | 'low-score'
  readonly isExpanded?: boolean
}

/**
 * Returns inline styles for an episode grid row matching the mockup.
 * Usage: <div style={episodeGridRowStyle({ status: 'ok' })}>{...columns}</div>
 */
export function episodeGridRowStyle({ status, isExpanded }: EpisodeGridRowStyleProps): React.CSSProperties {
  const borderLeftColor =
    status === 'missing' ? 'var(--error)' :
    status === 'low-score' ? 'var(--warning)' :
    'transparent'

  return {
    display: 'grid',
    gridTemplateColumns: EPISODE_GRID_COLUMNS,
    alignItems: 'center',
    padding: '10px 14px',
    backgroundColor: isExpanded ? 'var(--bg-surface-hover)' : 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    gap: '10px',
    borderLeft: `2px solid ${borderLeftColor}`,
    transition: 'all 0.15s',
  }
}

interface FormatBadgeProps {
  readonly format: string
}

/** Format badge pill — ASS / SRT / — */
export function FormatBadge({ format }: FormatBadgeProps) {
  if (!format || format === '') {
    return <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>&mdash;</span>
  }

  const label = format.replace('embedded_', '').toUpperCase()

  return (
    <span
      data-testid="format-badge"
      style={{
        fontSize: '11px',
        fontWeight: 600,
        padding: '2px 8px',
        borderRadius: '4px',
        backgroundColor: 'var(--bg-elevated)',
        color: 'var(--text-secondary)',
        width: 'fit-content',
      }}
    >
      {label}
    </span>
  )
}
