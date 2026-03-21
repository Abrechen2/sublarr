/**
 * MovieDetailPage — Detail view for a standalone movie.
 * Shows poster, metadata, and subtitle information.
 * No season/episode hierarchy — flat layout.
 */
import { useParams, useNavigate } from 'react-router-dom'
import { Loader2, FileVideo, ArrowLeft, Film } from 'lucide-react'
import { useMovieDetail } from '@/hooks/useApi'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import type { MovieDetail } from '@/lib/types'

// ─── MovieHero ────────────────────────────────────────────────────────────────

function MovieHero({ movie }: { movie: MovieDetail }) {
  return (
    <div
      className="rounded-lg overflow-hidden relative"
      style={{ border: '1px solid var(--border)', marginBottom: '16px' }}
    >
      <div
        className="relative z-10 p-6 flex items-start gap-6"
        style={{ background: 'linear-gradient(to right, var(--bg-surface) 70%, transparent)' }}
      >
        {/* Poster */}
        <div
          className="flex-shrink-0 rounded-lg overflow-hidden flex items-center justify-center"
          style={{
            width: 96,
            height: 140,
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
          }}
        >
          {movie.poster_url ? (
            <img
              src={movie.poster_url}
              alt={movie.title}
              className="w-full h-full object-cover"
            />
          ) : (
            <Film size={32} style={{ color: 'var(--text-muted)', opacity: 0.4 }} />
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <h1
            className="text-2xl font-bold mb-1 truncate"
            style={{ color: 'var(--text-primary)' }}
          >
            {movie.title}
          </h1>
          {movie.year && (
            <p className="text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
              {movie.year}
            </p>
          )}

          {/* Stat boxes */}
          <div className="flex items-center gap-3 flex-wrap">
            <div
              className="px-3 py-1.5 rounded-md text-xs font-medium"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
            >
              <span style={{ color: 'var(--text-muted)' }}>Missing</span>
              <span className="ml-1.5 font-semibold" style={{ color: 'var(--warning)' }}>
                {movie.wanted_count ?? 0}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── MovieDetailPage ─────────────────────────────────────────────────────────

export function MovieDetailPage() {
  const { id } = useParams<{ id: string }>()
  const movieId = id && !isNaN(Number(id)) ? Number(id) : null
  const { data: movie, isLoading, error } = useMovieDetail(movieId)
  const navigate = useNavigate()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64" data-testid="movie-loading">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  if (error || !movie) {
    return (
      <div className="space-y-4" data-testid="movie-error">
        <button
          onClick={() => navigate('/library')}
          className="flex items-center gap-2 text-sm transition-colors"
          style={{ color: 'var(--text-secondary)' }}
        >
          <ArrowLeft size={14} />
          Back to Library
        </button>
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <FileVideo size={32} className="mx-auto mb-3" style={{ color: 'var(--text-muted)', opacity: 0.4 }} />
          <p style={{ color: 'var(--error)' }}>Failed to load movie</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4 animate-in">
      {/* Breadcrumb navigation */}
      <Breadcrumb items={[{ label: 'Library', to: '/library' }, { label: movie.title }]} />

      {/* Hero Header */}
      <MovieHero movie={movie} />

      {/* Movie Info */}
      <div
        className="rounded-lg p-5"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          File Info
        </h2>
        <div className="space-y-2">
          <div className="flex items-start gap-2">
            <span className="text-xs font-medium w-24 flex-shrink-0" style={{ color: 'var(--text-muted)' }}>
              Path
            </span>
            <span
              className="text-xs break-all"
              style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
            >
              {movie.file_path}
            </span>
          </div>
          {movie.tmdb_id && (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium w-24 flex-shrink-0" style={{ color: 'var(--text-muted)' }}>
                TMDB
              </span>
              <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {movie.tmdb_id}
              </span>
            </div>
          )}
          {movie.imdb_id && (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium w-24 flex-shrink-0" style={{ color: 'var(--text-muted)' }}>
                IMDb
              </span>
              <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {movie.imdb_id}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
