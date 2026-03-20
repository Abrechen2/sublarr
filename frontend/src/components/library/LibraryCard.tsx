import type React from 'react'
import { Film, Tv, CheckCircle2 } from 'lucide-react'
import type { SeriesInfo, MovieInfo } from '@/lib/types'
import { ScoreBadge } from '@/components/shared/ScoreBadge'
import { cn } from '@/lib/utils'

interface LibraryCardProps {
  item: SeriesInfo | MovieInfo
  onClick: () => void
  style?: React.CSSProperties
  className?: string
}

function isSeries(item: SeriesInfo | MovieInfo): item is SeriesInfo {
  return 'missing_count' in item
}

function computeScore(item: SeriesInfo | MovieInfo): number | null {
  if (!isSeries(item)) return null
  const { episodes, episodes_with_files, missing_count } = item
  if (episodes === 0) return null
  if (missing_count > 0) return null
  return Math.round((episodes_with_files / episodes) * 100)
}

export function LibraryCard({ item, onClick, style, className }: LibraryCardProps) {
  const series = isSeries(item) ? item : null
  const missingCount = series?.missing_count ?? 0
  const score = computeScore(item)

  const isComplete = series
    ? series.missing_count === 0 && series.episodes > 0
    : false

  const episodeInfo = series
    ? `S${series.seasons} · ${series.episodes_with_files}/${series.episodes} eps`
    : null

  return (
    <div
      data-testid="library-card"
      onClick={onClick}
      className={cn(
        'cursor-pointer overflow-hidden group transition-all duration-200',
        className,
      )}
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        ...style,
      }}
      onMouseEnter={(e) => {
        const el = e.currentTarget
        el.style.transform = 'translateY(-2px)'
        el.style.border = '1px solid var(--accent)'
        el.style.boxShadow = '0 4px 16px rgba(0,0,0,0.18)'
      }}
      onMouseLeave={(e) => {
        const el = e.currentTarget
        el.style.transform = ''
        el.style.border = '1px solid var(--border)'
        el.style.boxShadow = ''
      }}
    >
      {/* Poster area */}
      <div className="relative" style={{ aspectRatio: '2/3' }}>
        {item.poster ? (
          <img
            src={item.poster}
            alt={item.title}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div
            className="w-full h-full flex items-center justify-center"
            style={{ backgroundColor: 'var(--bg-primary)' }}
          >
            {series ? (
              <Tv size={32} style={{ color: 'var(--text-muted)' }} />
            ) : (
              <Film size={32} style={{ color: 'var(--text-muted)' }} />
            )}
          </div>
        )}

        {/* Hover overlay */}
        <div
          className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none"
          style={{ backgroundColor: 'rgba(0,0,0,0.25)' }}
        />

        {/* Missing count badge — top-right */}
        {missingCount > 0 && (
          <span
            data-testid="library-card-missing-badge"
            className="absolute top-1.5 right-1.5 rounded-md px-1.5 py-0.5 text-[10px] font-bold text-white z-10"
            style={{ backgroundColor: 'var(--warning)' }}
          >
            {missingCount}
          </span>
        )}

        {/* Score badge — bottom-left of poster */}
        {score !== null && (
          <div
            data-testid="library-card-score-badge"
            className="absolute bottom-1.5 left-1.5 z-10"
          >
            <ScoreBadge score={score} />
          </div>
        )}
      </div>

      {/* Title bar */}
      <div className="px-2 py-2">
        <div className="flex items-start gap-1">
          <p
            className="text-xs font-medium truncate flex-1"
            style={{ color: 'var(--text-primary)' }}
            title={item.title}
          >
            {item.title}
          </p>
          {isComplete && (
            <CheckCircle2
              data-testid="library-card-complete-icon"
              size={12}
              className="shrink-0 mt-0.5"
              style={{ color: 'var(--success)' }}
            />
          )}
        </div>

        {/* Meta line */}
        {episodeInfo && (
          <p
            data-testid="library-card-meta"
            className="text-[10px] truncate mt-0.5"
            style={{ color: 'var(--text-muted)' }}
          >
            {episodeInfo}
          </p>
        )}

        {/* Profile name */}
        {series?.profile_name && (
          <p className="text-[10px] truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {series.profile_name}
          </p>
        )}
      </div>
    </div>
  )
}
