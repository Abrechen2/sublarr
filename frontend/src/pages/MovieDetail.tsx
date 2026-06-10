/**
 * MovieDetailPage — Detail view for a standalone movie.
 * Shows poster, metadata, and subtitle wanted items.
 */
import { useParams, useNavigate } from 'react-router-dom'
import { Loader2, FileVideo, ArrowLeft, Film, Search, SkipForward, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useMovieDetail, useWantedItems, useSearchWantedItem, useUpdateWantedStatus, useLanguageProfiles, useAssignProfile } from '@/hooks/useApi'
import { useMovieSubtitles } from '@/hooks/useLibraryApi'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { SubtitleActionsMenu } from '@/components/processing/SubtitleActionsMenu'
import type { MovieDetail, WantedItem } from '@/lib/types'
import type { SidecarSubtitle } from '@/types/library'

// ─── MovieHero ────────────────────────────────────────────────────────────────

function MovieHero({ movie }: { movie: MovieDetail }) {
  const { t } = useTranslation('library')

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
              <span style={{ color: 'var(--text-muted)' }}>{t('movie_detail.missing')}</span>
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

// ─── MovieWantedSection ───────────────────────────────────────────────────────

function MovieWantedSection({ movieId }: { movieId: number }) {
  const { t } = useTranslation('library')
  const { data: wanted, isLoading } = useWantedItems(
    1, 50, 'movie', undefined, undefined, false, movieId
  )
  const search = useSearchWantedItem()
  const updateStatus = useUpdateWantedStatus()

  const items = wanted?.data ?? []

  if (isLoading) {
    return (
      <div
        className="rounded-lg p-5"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        data-testid="movie-wanted-section"
      >
        <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div
      className="rounded-lg p-5"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      data-testid="movie-wanted-section"
    >
      <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
        {t('movie_detail.subtitles')}
      </h2>

      {items.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {t('movie_detail.no_missing')}
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item: WantedItem) => (
            <div
              key={item.id}
              className="flex items-center justify-between gap-3 py-2 px-3 rounded-md"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
            >
              <div className="flex items-center gap-2">
                <span
                  className="text-xs font-semibold px-2 py-0.5 rounded"
                  style={{
                    backgroundColor: item.status === 'wanted' ? 'rgba(239,68,68,0.15)' : 'var(--bg-elevated)',
                    color: item.status === 'wanted' ? 'var(--error)' : 'var(--text-secondary)',
                  }}
                >
                  {item.target_language.toUpperCase()}
                </span>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {item.status}
                  {item.search_count > 0 && ` · ${item.search_count} ${t('movie_detail.searches')}`}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {item.status === 'wanted' && (
                  <>
                    <button
                      onClick={() => search.mutate(item.id)}
                      disabled={search.isPending}
                      style={{
                        fontSize: '11px', fontWeight: 600, padding: '3px 10px',
                        borderRadius: '4px', backgroundColor: 'var(--accent)',
                        color: '#fff', border: 'none', cursor: 'pointer',
                        opacity: search.isPending ? 0.6 : 1,
                        display: 'flex', alignItems: 'center', gap: '4px',
                      }}
                    >
                      <Search size={10} />
                      {t('movie_detail.search')}
                    </button>
                    <button
                      onClick={() => updateStatus.mutate({ itemId: item.id, status: 'ignored' })}
                      disabled={updateStatus.isPending}
                      style={{
                        fontSize: '11px', padding: '3px 10px', borderRadius: '4px',
                        backgroundColor: 'transparent', color: 'var(--text-secondary)',
                        border: '1px solid var(--border)', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: '4px',
                      }}
                    >
                      <SkipForward size={10} />
                      {t('movie_detail.skip')}
                    </button>
                  </>
                )}
                {item.status === 'ignored' && (
                  <button
                    onClick={() => updateStatus.mutate({ itemId: item.id, status: 'wanted' })}
                    disabled={updateStatus.isPending}
                    style={{
                      fontSize: '11px', padding: '3px 10px', borderRadius: '4px',
                      backgroundColor: 'transparent', color: 'var(--text-muted)',
                      border: '1px solid var(--border)', cursor: 'pointer',
                      display: 'flex', alignItems: 'center', gap: '4px',
                    }}
                  >
                    <RotateCcw size={10} />
                    {t('movie_detail.re_enable')}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── MovieDetailPage ─────────────────────────────────────────────────────────

export function MovieDetailPage() {
  const { t } = useTranslation('library')
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
          {t('movie_detail.back_to_library')}
        </button>
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <FileVideo size={32} className="mx-auto mb-3" style={{ color: 'var(--text-muted)', opacity: 0.4 }} />
          <p style={{ color: 'var(--error)' }}>{t('movie_detail.load_error')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4 animate-in">
      {/* Breadcrumb navigation */}
      <Breadcrumb items={[{ label: t('title'), href: '/library' }, { label: movie.title }]} />

      {/* Hero Header */}
      <MovieHero movie={movie} />

      {/* Movie Info */}
      <div
        className="rounded-lg p-5"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
          {t('movie_detail.file_info')}
        </h2>
        <div className="space-y-2">
          <div className="flex items-start gap-2">
            <span className="text-xs font-medium w-24 flex-shrink-0" style={{ color: 'var(--text-muted)' }}>
              {t('movie_detail.path')}
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

      {/* Profile selector */}
      <MovieProfileSelector movieId={movie.id} movie={movie} />

      {/* Existing subtitle files */}
      <MovieSubtitlesSection movieId={movie.id} />

      {/* Missing subtitles / wanted items */}
      <MovieWantedSection movieId={movie.id} />
    </div>
  )
}

// ─── MovieProfileSelector ─────────────────────────────────────────────────────

function MovieProfileSelector({ movieId, movie }: { movieId: number; movie: MovieDetail }) {
  const { t } = useTranslation('library')
  const { data: profilesData } = useLanguageProfiles()
  const assignProfile = useAssignProfile()
  const profiles = profilesData ?? []

  return (
    <div
      className="rounded-lg p-5 flex items-center gap-3"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      data-testid="movie-profile-selector-card"
    >
      <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text-muted)', minWidth: '4rem' }}>
        {t('movie_detail.profile_label', 'Profile')}
      </span>
      <select
        aria-label={t('movie_detail.profile_select_aria', 'Select language profile')}
        data-testid="movie-profile-select"
        disabled={assignProfile.isPending}
        value={movie.profile_id ?? ''}
        onChange={(e) => {
          const id = Number(e.target.value)
          if (!isNaN(id) && id > 0) {
            assignProfile.mutate({ type: 'movie', arrId: movieId, profileId: id })
          }
        }}
        style={{
          padding: '3px 8px',
          borderRadius: '4px',
          fontSize: '11px',
          backgroundColor: 'var(--accent-bg)',
          color: 'var(--accent)',
          border: '1px solid var(--accent)',
          fontWeight: 600,
          cursor: assignProfile.isPending ? 'default' : 'pointer',
          opacity: assignProfile.isPending ? 0.6 : 1,
        }}
      >
        {profiles.length === 0 && (
          <option value="">{movie.profile_name || 'Default'}</option>
        )}
        {profiles.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}{p.is_default ? ' ★' : ''}
          </option>
        ))}
      </select>
    </div>
  )
}

// ─── MovieSubtitlesSection ────────────────────────────────────────────────────

function MovieSubtitlesSection({ movieId }: { movieId: number }) {
  const { t } = useTranslation('library')
  const { data, isLoading, refetch } = useMovieSubtitles(movieId)
  const subtitles = data?.subtitles ?? []

  if (isLoading) return null
  if (subtitles.length === 0) return null

  return (
    <div
      className="rounded-lg p-5"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      data-testid="movie-subtitles-section"
    >
      <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
        {t('movie_detail.existing_subtitles', 'Vorhandene Untertitel')}
      </h2>
      <div className="space-y-1.5">
        {subtitles.map((sub: SidecarSubtitle) => (
          <div
            key={sub.path}
            className="flex items-center justify-between gap-3 py-2 px-3 rounded-md"
            style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span
                className="text-xs font-semibold px-2 py-0.5 rounded shrink-0"
                style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
              >
                {sub.language.toUpperCase()}
              </span>
              <span
                className="text-xs px-1.5 py-0.5 rounded shrink-0"
                style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}
              >
                {sub.format.toUpperCase()}
              </span>
              {sub.modifier && (
                <span
                  className="text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0 uppercase tracking-wide"
                  style={{ backgroundColor: 'var(--warning-bg, #5a3d10)', color: 'var(--warning, #ffb84d)' }}
                  title={`Variant: ${sub.modifier.toUpperCase()}`}
                >
                  {sub.modifier}
                </span>
              )}
              <span className="text-xs truncate" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                {sub.path.split(/[/\\]/).pop()}
              </span>
            </div>
            <SubtitleActionsMenu subtitlePath={sub.path} onRefresh={() => void refetch()} />
          </div>
        ))}
      </div>
    </div>
  )
}
