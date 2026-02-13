import { useState } from 'react'
import { useBazarrStatus, useTranslateWanted } from '@/hooks/useApi'
import { Search, Play, Loader2 } from 'lucide-react'

export function WantedPage() {
  const { data: bazarr } = useBazarrStatus()
  const translateWanted = useTranslateWanted()
  const [maxEpisodes, setMaxEpisodes] = useState(5)

  if (!bazarr?.configured) {
    return (
      <div className="space-y-5">
        <h1>Wanted</h1>
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <div
            className="w-12 h-12 rounded-lg mx-auto mb-4 flex items-center justify-center"
            style={{ backgroundColor: 'var(--accent-subtle)' }}
          >
            <Search size={24} style={{ color: 'var(--text-muted)' }} />
          </div>
          <h2 className="text-base font-semibold mb-2">Bazarr Not Configured</h2>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Configure Bazarr in Settings to see the wanted list.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1>Wanted</h1>
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
              className="w-16 px-2 py-1.5 rounded-md text-sm"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
              }}
            />
          </div>
          <button
            onClick={() => translateWanted.mutate(maxEpisodes)}
            disabled={translateWanted.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-white hover:opacity-90"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {translateWanted.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Play size={14} />
            )}
            Translate Wanted
          </button>
        </div>
      </div>

      {/* Status */}
      <div
        className="rounded-lg p-4"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--text-muted)' }}>Bazarr Status</div>
            <div className="flex items-center gap-2">
              <div
                className="w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: bazarr.reachable ? 'var(--success)' : 'var(--error)' }}
              />
              <span className="text-sm">{bazarr.reachable ? 'Connected' : 'Error'}</span>
            </div>
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--text-muted)' }}>Wanted Episodes</div>
            <div className="text-lg font-bold" style={{ fontFamily: 'var(--font-mono)' }}>{bazarr.wanted_anime_count ?? 0}</div>
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--text-muted)' }}>Synced</div>
            <div className="text-lg font-bold" style={{ fontFamily: 'var(--font-mono)' }}>{bazarr.translations_synced ?? 0}</div>
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--text-muted)' }}>Last Action</div>
            <div className="text-sm">
              {translateWanted.isSuccess ? (
                <span style={{ color: 'var(--success)' }}>Started</span>
              ) : translateWanted.isError ? (
                <span style={{ color: 'var(--error)' }}>Failed</span>
              ) : (
                '\u2014'
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Result feedback */}
      {translateWanted.isSuccess && translateWanted.data && (
        <div
          className="rounded-lg p-4"
          style={{
            backgroundColor: 'var(--success-bg)',
            borderLeft: '3px solid var(--success)',
          }}
        >
          <div className="text-sm font-medium" style={{ color: 'var(--success)' }}>
            {translateWanted.data.episodes_queued} episodes queued for translation
          </div>
          {translateWanted.data.episodes?.map((ep: { series: string; episode: string; title: string }, i: number) => (
            <div key={i} className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
              {ep.series} &mdash; {ep.episode} &mdash; {ep.title}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
