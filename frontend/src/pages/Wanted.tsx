import { useState } from 'react'
import { useBazarrStatus, useTranslateWanted, useTranslateFile } from '@/hooks/useApi'
import { Search, Play, Loader2 } from 'lucide-react'

export function WantedPage() {
  const { data: bazarr } = useBazarrStatus()
  const translateWanted = useTranslateWanted()
  const translateFile = useTranslateFile()
  const [maxEpisodes, setMaxEpisodes] = useState(5)

  if (!bazarr?.configured) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Wanted</h1>
        <div
          className="rounded-xl p-8 text-center shadow-sm"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <Search size={48} className="mx-auto mb-4" style={{ color: 'var(--text-secondary)' }} />
          <h2 className="text-lg font-semibold mb-2">Bazarr Not Configured</h2>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Configure Bazarr in Settings to see the wanted list.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold">Wanted</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
            {bazarr.wanted_anime_count ?? 0} anime episodes missing subtitles
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>Max:</label>
            <input
              type="number"
              value={maxEpisodes}
              onChange={(e) => setMaxEpisodes(Number(e.target.value))}
              min={1}
              max={50}
              className="w-16 px-2 py-1.5 rounded-lg text-sm"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
          <button
            onClick={() => translateWanted.mutate(maxEpisodes)}
            disabled={translateWanted.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed text-white"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {translateWanted.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Play size={16} />
            )}
            Translate Wanted
          </button>
        </div>
      </div>

      {/* Status */}
      <div
        className="rounded-xl p-5 shadow-sm"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Bazarr Status</div>
            <div className="flex items-center gap-2">
              <div
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: bazarr.reachable ? 'var(--success)' : 'var(--error)' }}
              />
              <span className="text-sm">{bazarr.reachable ? 'Connected' : 'Error'}</span>
            </div>
          </div>
          <div>
            <div className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Wanted Episodes</div>
            <div className="text-lg font-bold">{bazarr.wanted_anime_count ?? 0}</div>
          </div>
          <div>
            <div className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Synced</div>
            <div className="text-lg font-bold">{bazarr.translations_synced ?? 0}</div>
          </div>
          <div>
            <div className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>Last Action</div>
            <div className="text-sm">
              {translateWanted.isSuccess ? '✓ Started' : translateWanted.isError ? '✗ Failed' : '—'}
            </div>
          </div>
        </div>
      </div>

      {/* Result feedback */}
      {translateWanted.isSuccess && translateWanted.data && (
        <div
          className="rounded-xl p-4"
          style={{ backgroundColor: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.3)' }}
        >
          <div className="text-sm font-medium" style={{ color: 'var(--success)' }}>
            ✓ {translateWanted.data.episodes_queued} episodes queued for translation
          </div>
          {translateWanted.data.episodes?.map((ep: { series: string; episode: string; title: string }, i: number) => (
            <div key={i} className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
              {ep.series} — {ep.episode} — {ep.title}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
