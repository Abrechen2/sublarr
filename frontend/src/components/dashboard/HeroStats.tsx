/**
 * HeroStats — 4-column hero stat grid at the top of the dashboard.
 *
 * Cards:
 *   1. Subtitles Total  — stats.total_subtitles (assumed field; defaults to 0)
 *   2. Missing          — wantedSummary.total, warning color if > 0
 *   3. Quality Avg      — stats.average_score (assumed field; defaults to 0)
 *   4. Low Score        — stats.low_score_count (assumed field; defaults to 0), upgrade color if > 0
 *
 * Note: total_subtitles, downloads_today, average_score, low_score_count are extended
 * fields not yet in the Stats type definition. They are accessed via optional chaining
 * with defaults of 0 until the backend exposes them.
 */
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { useStats } from '@/hooks/useSystemApi'
import { useWantedSummary } from '@/hooks/useWantedApi'

// ─── Types ────────────────────────────────────────────────────────────────────

type DeltaVariant = 'success' | 'warning' | 'upgrade' | 'neutral'
type CardColor = 'success' | 'warning' | 'accent' | 'upgrade'

interface HeroStatCardProps {
  readonly cardId: string
  readonly label: string
  readonly value: string | number
  readonly delta: string | number
  readonly deltaVariant: DeltaVariant
  readonly subText: string
  readonly color: CardColor
}

// ─── Delta badge ──────────────────────────────────────────────────────────────

const DELTA_COLOR_MAP: Readonly<Record<DeltaVariant, string>> = {
  success: 'var(--success)',
  warning: 'var(--warning)',
  upgrade: 'var(--upgrade, var(--accent))',
  neutral: 'var(--text-muted)',
}

function DeltaBadge({
  value,
  variant,
  testId,
}: {
  readonly value: string | number
  readonly variant: DeltaVariant
  readonly testId: string
}) {
  return (
    <span
      data-testid={testId}
      data-variant={variant}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '2px 7px',
        borderRadius: '999px',
        fontSize: '11px',
        fontWeight: 600,
        fontFamily: 'var(--font-mono)',
        color: DELTA_COLOR_MAP[variant],
        background: `color-mix(in srgb, ${DELTA_COLOR_MAP[variant]} 12%, transparent)`,
        lineHeight: 1.4,
      }}
    >
      {value}
    </span>
  )
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

const CARD_BORDER_COLOR_MAP: Readonly<Record<CardColor, string>> = {
  success: 'var(--success)',
  warning: 'var(--warning)',
  accent: 'var(--accent)',
  upgrade: 'var(--upgrade, var(--accent))',
}

function HeroStatCard({
  cardId,
  label,
  value,
  delta,
  deltaVariant,
  subText,
  color,
}: HeroStatCardProps) {
  return (
    <div
      data-testid="hero-stat-card"
      data-color={color}
      data-testid-named={`hero-stat-card-${cardId}`}
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '18px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
      }}
    >
      {/* Label — micro uppercase */}
      <span
        style={{
          fontSize: '10px',
          fontWeight: 600,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: 'var(--text-muted)',
          lineHeight: 1,
        }}
      >
        {label}
      </span>

      {/* Value row: big number + delta badge */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', flexWrap: 'wrap' }}>
        <span
          data-testid={`hero-stat-${cardId}`}
          style={{
            fontSize: '28px',
            fontWeight: 700,
            fontFamily: 'var(--font-mono)',
            color: CARD_BORDER_COLOR_MAP[color],
            lineHeight: 1,
          }}
        >
          {value}
        </span>
        <DeltaBadge value={delta} variant={deltaVariant} testId={`delta-${cardId}`} />
      </div>

      {/* Sub-text */}
      <span
        data-testid={`subtext-${cardId}`}
        style={{
          fontSize: '11px',
          color: 'var(--text-muted)',
          lineHeight: 1.3,
        }}
      >
        {subText}
      </span>
    </div>
  )
}

// ─── HeroStats ────────────────────────────────────────────────────────────────

export function HeroStats() {
  const { t } = useTranslation('common')
  const { data: stats } = useStats()
  const { data: wantedSummary } = useWantedSummary()

  // Extended fields not yet in the Stats type — accessed safely with defaults.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const extStats = stats as any

  const totalSubtitles: number = extStats?.total_subtitles ?? 0
  const downloadsToday: number = extStats?.downloads_today ?? 0
  const averageScore: number = extStats?.average_score ?? 0
  const lowScoreCount: number = extStats?.low_score_count ?? 0
  const missingTotal: number = wantedSummary?.total ?? 0

  return (
    <div
      data-testid="hero-stats"
      className={cn(
        'grid gap-4',
        'grid-cols-2 sm:grid-cols-2 lg:grid-cols-4',
      )}
    >
      {/* Card 1: Subtitles Total */}
      <div data-testid="hero-stat-card-subtitles-total" data-color="success">
        <HeroStatCard
          cardId="subtitles-total"
          label={t('heroStats.subtitlesTotal')}
          value={totalSubtitles}
          delta={`+${downloadsToday} ${t('heroStats.today')}`}
          deltaVariant="success"
          subText={t('heroStats.subtitlesTotalSub')}
          color="success"
        />
      </div>

      {/* Card 2: Missing */}
      <div data-testid="hero-stat-card-missing" data-color={missingTotal > 0 ? 'warning' : 'success'}>
        <HeroStatCard
          cardId="missing"
          label={t('heroStats.missing')}
          value={missingTotal}
          delta={missingTotal > 0 ? `${missingTotal} ${t('heroStats.pending')}` : t('heroStats.allGood')}
          deltaVariant={missingTotal > 0 ? 'warning' : 'success'}
          subText={t('heroStats.missingSub')}
          color={missingTotal > 0 ? 'warning' : 'success'}
        />
      </div>

      {/* Card 3: Quality Avg */}
      <div data-testid="hero-stat-card-quality-avg" data-color="accent">
        <HeroStatCard
          cardId="quality-avg"
          label={t('heroStats.qualityAvg')}
          value={averageScore > 0 ? averageScore.toFixed(1) : '—'}
          delta={t('heroStats.qualityAvgDelta')}
          deltaVariant="neutral"
          subText={t('heroStats.qualityAvgSub')}
          color="accent"
        />
      </div>

      {/* Card 4: Low Score */}
      <div data-testid="hero-stat-card-low-score" data-color={lowScoreCount > 0 ? 'upgrade' : 'success'}>
        <HeroStatCard
          cardId="low-score"
          label={t('heroStats.lowScore')}
          value={lowScoreCount}
          delta={lowScoreCount > 0 ? t('heroStats.lowScoreUpgrade') : t('heroStats.allGood')}
          deltaVariant={lowScoreCount > 0 ? 'upgrade' : 'success'}
          subText={t('heroStats.lowScoreSub')}
          color={lowScoreCount > 0 ? 'upgrade' : 'success'}
        />
      </div>
    </div>
  )
}

export default HeroStats
