import { useState } from 'react'

interface Props {
  score: number
  breakdown: Record<string, number>
  className?: string
}

const LABELS: Record<string, string> = {
  series: 'Series title', hash: 'File hash', year: 'Year',
  season: 'Season', episode: 'Episode', release_group: 'Release group',
  source: 'Source (BluRay/WEB)', audio_codec: 'Audio codec', resolution: 'Resolution',
  hearing_impaired: 'Hearing impaired', format_bonus: 'ASS format bonus',
  provider_modifier: 'Provider bonus/penalty', uploader_trust: 'Uploader trust',
  hi_preference: 'HI preference', forced_preference: 'Forced preference',
}

function badgeColor(score: number): 'success' | 'warning' | 'muted' {
  if (score >= 300) return 'success'
  if (score >= 200) return 'warning'
  return 'muted'
}

export function ScoreBreakdown({ score, breakdown, className }: Props) {
  const [visible, setVisible] = useState(false)
  const color = badgeColor(score)
  const hasEntries = Object.keys(breakdown).length > 0

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
            Score breakdown
          </div>
          {!hasEntries && (
            <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>No breakdown available</div>
          )}
          {hasEntries && Object.entries(breakdown)
            .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
            .map(([key, pts]) => (
              <div key={key} style={{
                display: 'flex', justifyContent: 'space-between', gap: '12px', padding: '2px 0',
                color: pts < 0 ? 'var(--error)' : 'var(--text-primary)',
              }}>
                <span style={{ color: 'var(--text-secondary)' }}>{LABELS[key] ?? key}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                  {pts > 0 ? '+' : ''}{pts}
                </span>
              </div>
            ))}
          {hasEntries && (
            <>
              <div style={{ borderTop: '1px solid var(--border)', margin: '6px 0' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                <span>Total</span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{score}</span>
              </div>
            </>
          )}
        </div>
      )}
    </span>
  )
}
