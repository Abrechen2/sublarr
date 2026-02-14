import { useState } from 'react'
import { useLibrary, useLanguageProfiles, useAssignProfile } from '@/hooks/useApi'
import { Tv, Film, Loader2, Settings } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { SeriesInfo, MovieInfo, LanguageProfile } from '@/lib/types'

type Tab = 'series' | 'movies'

function LibraryCard({ item, type, profiles, onAssign }: {
  item: SeriesInfo | MovieInfo
  type: Tab
  profiles?: LanguageProfile[]
  onAssign?: (arrId: number, profileId: number) => void
}) {
  const isSeries = type === 'series'
  return (
    <div
      className="rounded-lg overflow-hidden transition-all duration-200 hover:shadow-lg group"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--border-hover)'
        e.currentTarget.style.transform = 'translateY(-2px)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border)'
        e.currentTarget.style.transform = 'translateY(0)'
      }}
    >
      <div className="aspect-[2/3] relative overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
        {item.poster ? (
          <img
            src={item.poster}
            alt={item.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            {isSeries ? (
              <Tv size={28} style={{ color: 'var(--text-muted)' }} />
            ) : (
              <Film size={28} style={{ color: 'var(--text-muted)' }} />
            )}
          </div>
        )}
      </div>
      <div className="p-2.5">
        <div className="text-sm font-medium truncate" title={item.title}>
          {item.title}
        </div>
        <div className="flex items-center justify-between mt-1">
          <span className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            {item.year || '\u2014'}
          </span>
          {isSeries && 'episodes' in item && (
            <span className="text-xs" style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
              {(item as SeriesInfo).episodes_with_files || 0}/{(item as SeriesInfo).episodes}
            </span>
          )}
          {!isSeries && 'has_file' in item && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded font-medium"
              style={{
                backgroundColor: (item as MovieInfo).has_file ? 'var(--success-bg)' : 'var(--error-bg)',
                color: (item as MovieInfo).has_file ? 'var(--success)' : 'var(--error)',
              }}
            >
              {(item as MovieInfo).has_file ? 'On Disk' : 'Missing'}
            </span>
          )}
        </div>
        {profiles && profiles.length > 1 && onAssign && (
          <select
            className="mt-1.5 w-full text-[10px] px-1.5 py-1 rounded"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
            }}
            defaultValue=""
            onChange={(e) => {
              if (e.target.value) onAssign(item.id, Number(e.target.value))
            }}
          >
            <option value="">Default Profile</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.target_languages.join(', ')})
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  )
}

export function LibraryPage() {
  const { data: library, isLoading } = useLibrary()
  const { data: profiles } = useLanguageProfiles()
  const assignProfile = useAssignProfile()
  const [activeTab, setActiveTab] = useState<Tab>('series')
  const navigate = useNavigate()

  const handleAssign = (type: 'series' | 'movie', arrId: number, profileId: number) => {
    assignProfile.mutate({ type, arrId, profileId })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  const series = library?.series || []
  const movies = library?.movies || []
  const items = activeTab === 'series' ? series : movies
  const isEmpty = series.length === 0 && movies.length === 0

  if (isEmpty) {
    return (
      <div className="space-y-5">
        <h1>Library</h1>
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <div
            className="w-12 h-12 rounded-lg mx-auto mb-4 flex items-center justify-center"
            style={{ backgroundColor: 'var(--accent-subtle)' }}
          >
            <Tv size={24} style={{ color: 'var(--text-muted)' }} />
          </div>
          <h2 className="text-base font-semibold mb-2">No Library Data</h2>
          <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
            Configure Sonarr and/or Radarr in Settings to see your library.
          </p>
          <button
            onClick={() => navigate('/settings')}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-white hover:opacity-90"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            <Settings size={14} />
            Go to Settings
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1>Library</h1>
        <div className="flex gap-1.5">
          <button
            onClick={() => setActiveTab('series')}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
            style={{
              backgroundColor: activeTab === 'series' ? 'var(--accent-bg)' : 'var(--bg-surface)',
              color: activeTab === 'series' ? 'var(--accent)' : 'var(--text-secondary)',
              border: `1px solid ${activeTab === 'series' ? 'var(--accent-dim)' : 'var(--border)'}`,
            }}
          >
            <Tv size={12} />
            Series ({series.length})
          </button>
          <button
            onClick={() => setActiveTab('movies')}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
            style={{
              backgroundColor: activeTab === 'movies' ? 'var(--accent-bg)' : 'var(--bg-surface)',
              color: activeTab === 'movies' ? 'var(--accent)' : 'var(--text-secondary)',
              border: `1px solid ${activeTab === 'movies' ? 'var(--accent-dim)' : 'var(--border)'}`,
            }}
          >
            <Film size={12} />
            Movies ({movies.length})
          </button>
        </div>
      </div>

      {items.length === 0 ? (
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            No {activeTab} found. Configure {activeTab === 'series' ? 'Sonarr' : 'Radarr'} in Settings.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          {activeTab === 'series'
            ? series.map((item: SeriesInfo) => (
                <LibraryCard
                  key={item.id}
                  item={item}
                  type="series"
                  profiles={profiles}
                  onAssign={(arrId, profileId) => handleAssign('series', arrId, profileId)}
                />
              ))
            : movies.map((item: MovieInfo) => (
                <LibraryCard
                  key={item.id}
                  item={item}
                  type="movies"
                  profiles={profiles}
                  onAssign={(arrId, profileId) => handleAssign('movie', arrId, profileId)}
                />
              ))}
        </div>
      )}
    </div>
  )
}
