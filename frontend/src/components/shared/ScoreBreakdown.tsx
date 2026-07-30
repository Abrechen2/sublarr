import { useState } from 'react'
import { useTranslation } from 'react-i18next'

interface Props {
  score: number
  breakdown: Record<string, number>
  className?: string
}

// Breakdown component keys — resolved via i18n (common:score_breakdown.labels.*).
// Keys missing here (unknown providers/rules) fall back to the raw key.
const KNOWN_KEYS = [
  'series', 'title', 'hash', 'year', 'season', 'episode', 'release_group',
  'source', 'audio_codec', 'resolution', 'video_codec', 'hearing_impaired',
  'format_bonus', 'provider_modifier', 'uploader_trust', 'hi_preference',
  'forced_preference', 'fansub_preferred', 'fansub_excluded', 'video_codec_bonus',
] as const

function badgeColor(score: number): 'success' | 'warning' | 'muted' {
  if (score >= 300) return 'success'
  if (score >= 200) return 'warning'
  return 'muted'
}

export function ScoreBreakdown({ score, breakdown, className }: Props) {
  const { t: tc } = useTranslation('common')
  const [visible, setVisible] = useState(false)
  const color = badgeColor(score)
  const hasEntries = Object.keys(breakdown).length > 0

  const labelFor = (key: string): string => {
    if (key.startsWith('rule:')) {
      return tc('score_breakdown.rule', { id: key.slice(5) })
    }
    if ((KNOWN_KEYS as readonly string[]).includes(key)) {
      return tc(`score_breakdown.labels.${key}`)
    }
    return key
  }

  const badgeStyle: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center',
    padding: '2px 7px', borderRadius: '9999px',
    fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 600,
    cursor: 'help',
    background: color === 'success'
      ? 'color-mix(in srgb, var(--success) 15%, transparent)'
      : color === 'warning'
        ? 'color-mix(in srgb, var(--warning) 15%, transparent)'
        : 'color-mix(in srgb, var(--text-muted) 10%, transparent)',
    color: color === 'success' ? 'var(--success)'
         : color === 'warning' ? 'var(--warning)'
         : 'var(--text-muted)',
    border: `1px solid ${
      color === 'success' ? 'var(--success)'
    : color === 'warning' ? 'var(--warning)'
    : 'var(--border)'}`,
  }

  return (
    <span
      className={className}
      style={{ position: 'relative', display: 'inline-block' }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
      tabIndex={0}
      aria-label={`Score ${score}`}
    >
      <span style={badgeStyle}>{score}</span>

      {visible && (
        <div
          role="tooltip"
          style={{
            position: 'absolute', bottom: 'calc(100% + 6px)', left: '50%',
            transform: 'translateX(-50%)', zIndex: 50, minWidth: '220px',
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
            borderRadius: '6px', padding: '10px 12px',
            boxShadow: '0 4px 16px rgba(0,0,0,0.3)', fontSize: '12px',
            color: 'var(--text-primary)', pointerEvents: 'none',
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: '6px', color: 'var(--text-secondary)' }}>
            {tc('score_breakdown.title')}
          </div>
          {!hasEntries && (
            <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>{tc('ui.no_breakdown')}</div>
          )}
          {hasEntries && Object.entries(breakdown)
            .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
            .map(([key, pts]) => (
              <div key={key} style={{
                display: 'flex', justifyContent: 'space-between', gap: '12px', padding: '2px 0',
                color: pts < 0 ? 'var(--error)' : 'var(--text-primary)',
              }}>
                <span style={{ color: 'var(--text-secondary)' }}>{labelFor(key)}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                  {pts > 0 ? '+' : ''}{pts}
                </span>
              </div>
            ))}
          {hasEntries && (
            <>
              <div style={{ borderTop: '1px solid var(--border)', margin: '6px 0' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                <span>{tc('ui.total')}</span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{score}</span>
              </div>
            </>
          )}
        </div>
      )}
    </span>
  )
}
