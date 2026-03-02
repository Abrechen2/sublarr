import { Film } from 'lucide-react'
import type { SeriesInfo, MovieInfo } from '@/lib/types'

interface LibraryGridCardProps {
  item: SeriesInfo | MovieInfo
  onClick: () => void
}

function isSeries(item: SeriesInfo | MovieInfo): item is SeriesInfo {
  return 'missing_count' in item
}

export function LibraryGridCard({ item, onClick }: LibraryGridCardProps) {
  const missingCount = isSeries(item) ? item.missing_count : 0

  return (
    <div
      onClick={onClick}
      className="cursor-pointer rounded-lg overflow-hidden group"
      style={{ border: '1px solid var(--border)' }}
    >
      {/* Image area — overlays scoped here so they don't cover the title bar */}
      <div className="relative">
        {item.poster ? (
          <img
            src={item.poster}
            alt={item.title}
            className="w-full object-cover"
            style={{ aspectRatio: '2/3' }}
            loading="lazy"
          />
        ) : (
          <div
            className="w-full flex items-center justify-center"
            style={{ aspectRatio: '2/3', backgroundColor: 'var(--bg-surface)' }}
          >
            <Film size={32} style={{ color: 'var(--text-muted)' }} />
          </div>
        )}

        {/* Hover overlay */}
        <div
          className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-150"
          style={{ backgroundColor: 'rgba(0,0,0,0.3)' }}
        />

        {/* Missing badge — after hover overlay in DOM so it renders on top */}
        {missingCount > 0 && (
          <span
            className="absolute top-1 right-1 rounded px-1.5 py-0.5 text-[10px] font-bold text-white"
            style={{ backgroundColor: 'var(--error)' }}
          >
            {missingCount}
          </span>
        )}
      </div>

      {/* Title bar */}
      <div
        className="px-2 py-1.5"
        style={{ backgroundColor: 'var(--bg-surface)' }}
      >
        <p
          className="text-xs font-medium truncate"
          style={{ color: 'var(--text-primary)' }}
          title={item.title}
        >
          {item.title}
        </p>
        {isSeries(item) && item.profile_name && (
          <p className="text-[10px] truncate" style={{ color: 'var(--text-muted)' }}>
            {item.profile_name}
          </p>
        )}
      </div>
    </div>
  )
}
