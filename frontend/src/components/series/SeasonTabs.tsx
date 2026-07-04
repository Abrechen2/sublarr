// frontend/src/components/series/SeasonTabs.tsx
import { useTranslation } from 'react-i18next'

interface SeasonTabsProps {
  readonly seasons: number[]
  readonly activeSeason: number
  readonly onSeasonChange: (season: number) => void
}

export function SeasonTabs({ seasons, activeSeason, onSeasonChange }: SeasonTabsProps) {
  const { t } = useTranslation('library')

  return (
    // Pill-container matching .season-tabs in mockup
    <div style={{
      display: 'flex', gap: '2px',
      background: 'var(--bg-surface)', borderRadius: 'var(--radius-md)',
      padding: '3px', width: 'fit-content', marginBottom: '14px',
    }}>
      {seasons.map((s) => (
        <button
          key={s}
          data-testid={`season-tab-${s}`}
          onClick={() => onSeasonChange(s)}
          style={{
            padding: '6px 16px',
            borderRadius: '7px',
            fontSize: '12px',
            fontWeight: 500,
            cursor: 'pointer',
            transition: 'all 0.15s',
            border: 'none',
            backgroundColor: s === activeSeason ? 'var(--bg-elevated)' : 'transparent',
            color: s === activeSeason ? 'var(--text-primary)' : 'var(--text-secondary)',
            boxShadow: s === activeSeason ? '0 1px 3px rgba(0,0,0,0.2)' : 'none',
          }}
        >
          {s === 0
            ? t('series_detail.specials')
            : t('series_detail.season', { number: s })}
        </button>
      ))}
    </div>
  )
}
