import type React from 'react'
import { useTranslation } from 'react-i18next'
import type { EpisodeRowStatus } from '@/components/library/EpisodeRow'

/** CSS grid template matching the mockup exactly */
export const EPISODE_GRID_COLUMNS = '28px 50px 1fr 90px minmax(180px,1.5fr) 170px'

/** Episode header row — column labels */
export function EpisodeGridHeader() {
  const { t } = useTranslation('library')
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
      <span /> {/* checkbox placeholder */}
      <span>#</span>
      <span>{t('episode_ui.col_episode')}</span>
      <span>{t('episode_ui.col_audio')}</span>
      <span>{t('episode_ui.col_subtitles')}</span>
      <span style={{ textAlign: 'right' }}>{t('episode_ui.col_actions')}</span>
    </div>
  )
}

interface EpisodeGridRowStyleProps {
  readonly status: EpisodeRowStatus
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

interface ScoreCellProps {
  readonly status: EpisodeRowStatus
  readonly score: number | null
  readonly isSearching?: boolean
}

/** Score badge pill — color-tiered by score value, or contextual state badges. */
export function ScoreCell({ status, score, isSearching }: ScoreCellProps) {
  const { t } = useTranslation('library')
  if (isSearching) {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: '28px', height: '20px', borderRadius: '4px',
        backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', fontSize: '13px',
      }}>⌛</span>
    )
  }
  if (status === 'missing') {
    return (
      <span style={{
        fontSize: '10px', fontWeight: 700, padding: '2px 6px', borderRadius: '4px',
        backgroundColor: 'rgba(239,68,68,0.15)', color: 'var(--error)',
      }}>{t('episode_ui.missing')}</span>
    )
  }
  if (score === null) {
    return <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>&mdash;</span>
  }
  // Score badge matches mockup .ep-score — background pill with color per tier
  const bgColor = score >= 80 ? 'var(--success-bg)' : score >= 60 ? 'var(--accent-bg)' : 'var(--warning-bg)'
  const color = score >= 80 ? 'var(--success)' : score >= 60 ? 'var(--accent)' : 'var(--warning)'
  return (
    <span style={{
      fontSize: '12px', fontWeight: 700,
      padding: '3px 10px', borderRadius: '6px',
      textAlign: 'center', width: 'fit-content',
      backgroundColor: bgColor, color,
    }}>{score}</span>
  )
}

/** Provider name cell — plain text or em-dash placeholder. */
export function ProviderCell({ provider }: { provider: string | null }) {
  if (!provider) return <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>&mdash;</span>
  return <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{provider}</span>
}

interface EpisodeInlineActionsProps {
  readonly status: EpisodeRowStatus
  readonly isSearching: boolean
  readonly onSearch: () => void
  readonly onSkip: () => void
  readonly onFindBetter: () => void
  readonly onAccept: () => void
  readonly onSync: () => void
  readonly onDelete: () => void
  readonly onMore: () => void  // opens the existing EpisodeActionMenu
}

/** Inline action buttons for an episode row, adaptive to the row's status. */
export function EpisodeInlineActions({
  status, isSearching, onSearch, onSkip, onFindBetter, onAccept, onSync, onDelete: _onDelete, onMore
}: EpisodeInlineActionsProps) {
  const { t } = useTranslation('library')
  if (isSearching) {
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button disabled style={{
          fontSize: '11px', padding: '3px 10px', borderRadius: '4px', opacity: 0.4,
          backgroundColor: 'var(--bg-elevated)', color: 'var(--text-muted)',
          border: '1px solid var(--border)',
        }}>{t('episode_ui.searching_ellipsis')}</button>
      </div>
    )
  }
  if (status === 'missing') {
    return (
      <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
        <button
          onClick={onSearch}
          style={{
            fontSize: '11px', fontWeight: 600, padding: '3px 10px', borderRadius: '4px',
            backgroundColor: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer',
          }}
        >{t('episode_ui.search')}</button>
        <button
          onClick={onSkip}
          style={{
            fontSize: '11px', padding: '3px 10px', borderRadius: '4px',
            backgroundColor: 'transparent', color: 'var(--text-secondary)',
            border: '1px solid var(--border)', cursor: 'pointer',
          }}
        >{t('episode_ui.skip')}</button>
      </div>
    )
  }
  if (status === 'low-score') {
    return (
      <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
        <button
          onClick={onFindBetter}
          style={{
            fontSize: '11px', fontWeight: 600, padding: '3px 10px', borderRadius: '4px',
            backgroundColor: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer',
          }}
        >{t('episode_ui.find_better')}</button>
        <button
          onClick={onAccept}
          style={{
            fontSize: '11px', padding: '3px 10px', borderRadius: '4px',
            backgroundColor: 'transparent', color: 'var(--text-secondary)',
            border: '1px solid var(--border)', cursor: 'pointer',
          }}
        >{t('episode_ui.accept')}</button>
      </div>
    )
  }
  // status === 'ok' or 'no-file'
  return (
    <div style={{ display: 'flex', gap: '4px', justifyContent: 'flex-end', alignItems: 'center' }}>
      <button
        onClick={onSync}
        title={t('auto_sync')}
        style={{
          padding: '4px', borderRadius: '4px', border: 'none', cursor: 'pointer',
          backgroundColor: 'transparent', color: 'var(--text-muted)',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
        onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
      >↻</button>
      <button
        onClick={onMore}
        title={t('more_actions')}
        style={{
          padding: '4px', border: 'none', cursor: 'pointer',
          backgroundColor: 'var(--accent)',
          display: 'block', width: '8px', height: '8px', borderRadius: '50%',
        }}
      />
    </div>
  )
}
