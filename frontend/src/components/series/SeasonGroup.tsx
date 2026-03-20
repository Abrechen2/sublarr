import { useState, useMemo, useCallback } from 'react'
import { ChevronDown, ChevronRight, Loader2, Play } from 'lucide-react'
import { EpisodeRow } from '@/components/library/EpisodeRow'
import { EpisodeActionMenu } from '@/components/episodes/EpisodeActionMenu'
import { SubBadge } from './SubBadge'
import { EpisodeSearchPanel } from './EpisodeSearchPanel'
import { EpisodeHistoryPanel } from './EpisodeHistoryPanel'
import { TrackPanel } from '@/components/tracks/TrackPanel'
import { episodeGridRowStyle, FormatBadge } from './EpisodeGrid'
import { deriveSubtitlePath } from './seriesUtils'
import { startWantedBatchSearch } from '@/api/client'
import { useBatchTranslate } from '@/hooks/useApi'
import type { EpisodeInfo, WantedSearchResponse, EpisodeHistoryEntry, SidecarSubtitle } from '@/lib/types'

export interface SeasonGroupProps {
  readonly season: number
  readonly episodes: EpisodeInfo[]
  readonly targetLanguages: string[]
  readonly seriesId: number | null
  readonly isExtracting?: boolean
  readonly onExtract?: () => void
  readonly expandedEp: { id: number; mode: 'search' | 'history' | 'glossary' | 'tracks' } | null
  readonly onSearch: (ep: EpisodeInfo) => void
  readonly onInteractiveSearch: (ep: EpisodeInfo) => void
  readonly onHistory: (ep: EpisodeInfo) => void
  readonly onTracks: (ep: EpisodeInfo) => void
  readonly onClose: () => void
  readonly searchResults: WantedSearchResponse | null
  readonly searchLoading: boolean
  readonly historyEntries: EpisodeHistoryEntry[]
  readonly historyLoading: boolean
  readonly onProcess: (wantedId: number) => void
  readonly onPreviewSub: (filePath: string) => void
  readonly onEditSub: (filePath: string) => void
  readonly onCompare: (ep: EpisodeInfo) => void
  readonly onSync: (filePath: string) => void
  readonly onAutoSync: (subtitlePath: string, videoPath: string) => void
  readonly onVideoSync: (ep: EpisodeInfo, subtitlePath: string) => void
  readonly onHealthCheck: (filePath: string) => void
  readonly healthScores: Record<string, number | null>
  readonly onOpenEditor: (filePath: string) => void
  readonly sidecarMap: Record<string, SidecarSubtitle[]>
  readonly onDeleteSidecar: (path: string) => Promise<void>
  readonly onOpenCleanupModal: () => void
  readonly onPreview: (ep: EpisodeInfo) => void
  readonly streamingEnabled: boolean
  readonly onRefreshSidecars?: () => void
  readonly t: (key: string, opts?: Record<string, unknown>) => string
}

export function SeasonGroup({ season, episodes, targetLanguages, seriesId: _seriesId, isExtracting, onExtract, expandedEp, onSearch, onInteractiveSearch, onHistory, onTracks, onClose, searchResults, searchLoading, historyEntries, historyLoading, onProcess, onPreviewSub, onEditSub, onCompare, onSync, onAutoSync, onVideoSync, onHealthCheck, healthScores: _healthScores, onOpenEditor, sidecarMap: _sidecarMap, onDeleteSidecar: _onDeleteSidecar, onOpenCleanupModal, onPreview, streamingEnabled, onRefreshSidecars: _onRefreshSidecars, t }: SeasonGroupProps) {
  const [expanded, setExpanded] = useState(true)
  const [selectedEpisodes, setSelectedEpisodes] = useState<Set<number>>(new Set())

  const allSelectableIds = useMemo(
    () => episodes.map(e => e.id).filter((id): id is number => id != null),
    [episodes]
  )

  const toggleEpisode = useCallback((id: number) => {
    setSelectedEpisodes(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }, [])

  const selectAll = useCallback(() => setSelectedEpisodes(new Set(allSelectableIds)), [allSelectableIds])
  const clearAll = useCallback(() => setSelectedEpisodes(new Set()), [])
  const batchTranslateMutation = useBatchTranslate()

  return (
    <div>
      {/* Season Header — pill-shaped tab style */}
      <div
        className="flex items-center"
        style={{
          backgroundColor: expanded ? 'var(--bg-elevated)' : 'var(--bg-surface)',
          borderBottom: expanded ? '1px solid var(--border)' : 'none',
          transition: 'background-color 0.15s',
        }}
      >
        <button
          data-testid="season-group"
          onClick={() => setExpanded(!expanded)}
          className="flex-1 flex items-center gap-2 text-left transition-colors"
          style={{ padding: '8px 16px' }}
        >
          {expanded ? (
            <ChevronDown size={14} style={{ color: 'var(--accent)' }} />
          ) : (
            <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
          )}
          <span style={{ fontSize: '13px', fontWeight: 600 }}>
            {t('series_detail.season', { number: season })}
          </span>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '4px' }}>
            ({t('series_detail.episodes_count', { count: episodes.length })})
          </span>
        </button>
        {expanded && (
          <div className="pr-4 flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={allSelectableIds.length > 0 && selectedEpisodes.size === allSelectableIds.length}
              onChange={() => selectedEpisodes.size === allSelectableIds.length ? clearAll() : selectAll()}
              className="rounded"
              style={{ accentColor: 'var(--accent)' }}
              title="Select all episodes in this season"
            />
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>All</span>
          </div>
        )}
      </div>

      {/* Episodes */}
      {expanded && (
        <div>
          {episodes
            .sort((a, b) => b.episode - a.episode)
            .map((ep) => {
              const isExpanded = expandedEp?.id === ep.id
              const mode = expandedEp?.mode

              return (
                <EpisodeRow
                  key={ep.id}
                  ep={ep}
                  targetLanguages={targetLanguages}
                >
                <div data-testid="episode-row">
                  <div
                    style={episodeGridRowStyle({
                      status: !ep.has_file ? 'missing' : targetLanguages.some(lang => !ep.subtitles[lang]) ? 'missing' : 'ok',
                      isExpanded,
                    })}
                    onMouseEnter={(e) => {
                      if (!isExpanded) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                    }}
                    onMouseLeave={(e) => {
                      if (!isExpanded) e.currentTarget.style.backgroundColor = 'var(--bg-surface)'
                    }}
                  >
                    {/* Column 1: Episode number */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <input
                        type="checkbox"
                        checked={selectedEpisodes.has(ep.id)}
                        onChange={() => toggleEpisode(ep.id)}
                        className="rounded"
                        style={{ accentColor: 'var(--accent)' }}
                        onClick={(e) => e.stopPropagation()}
                      />
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                        E{String(ep.episode).padStart(2, '0')}
                      </span>
                    </div>

                    {/* Column 2: Episode title + file path + subtitle badges */}
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '13px', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={ep.title}>
                        {ep.title || 'TBA'}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: '2px' }}>
                        {ep.has_file ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                            <span>{ep.file_path.split(/[/\\]/).pop() || ep.file_path}</span>
                            {/* Compact subtitle badges */}
                            {targetLanguages.map(lang => {
                              const subFormat = ep.subtitles[lang] || ''
                              return <SubBadge key={lang} lang={lang} format={subFormat} />
                            })}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--error)' }}>No file</span>
                        )}
                      </div>
                    </div>

                    {/* Column 3: Format */}
                    <div>
                      <FormatBadge format={targetLanguages.length > 0 ? (ep.subtitles[targetLanguages[0]] || '') : ''} />
                    </div>

                    {/* Column 4: Provider (not in data model yet) */}
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>&mdash;</div>

                    {/* Column 5: Score (not in data model yet) */}
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>&mdash;</div>

                    {/* Column 6: Actions */}
                    <div style={{ display: 'flex', gap: '4px', justifyContent: 'flex-end' }}>
                      {streamingEnabled && ep.has_file && ep.file_path && (
                        <button
                          onClick={() => onPreview(ep)}
                          className="hover-surface p-1 rounded text-[var(--text-muted)] hover:text-[var(--accent)]"
                          title="Preview in player"
                          aria-label={`Preview episode ${ep.episode}`}
                        >
                          <Play size={14} />
                        </button>
                      )}
                      {(() => {
                        const firstLang = ep.has_file
                          ? Object.entries(ep.subtitles).find(([, f]) => f === 'ass' || f === 'srt')
                          : null
                        const firstSubPath = firstLang
                          ? deriveSubtitlePath(ep.file_path, firstLang[0], firstLang[1])
                          : null
                        const hasMultipleSubs = ep.has_file
                          ? Object.values(ep.subtitles).filter(f => f === 'ass' || f === 'srt').length >= 2
                          : false
                        return (
                          <EpisodeActionMenu
                            ep={ep}
                            isExpanded={isExpanded}
                            mode={mode}
                            searchLoading={searchLoading}
                            historyLoading={historyLoading}
                            firstSubPath={firstSubPath}
                            hasMultipleSubs={hasMultipleSubs}
                            onSearch={() => onSearch(ep)}
                            onEditSub={onEditSub}
                            onPreviewSub={onPreviewSub}
                            onCompare={() => onCompare(ep)}
                            onSync={onSync}
                            onAutoSync={onAutoSync}
                            onVideoSync={(subtitlePath) => onVideoSync(ep, subtitlePath)}
                            onHealthCheck={onHealthCheck}
                            onTracks={() => onTracks(ep)}
                            onInteractiveSearch={() => onInteractiveSearch(ep)}
                            onHistory={() => onHistory(ep)}
                            onClose={onClose}
                          />
                        )
                      })()}
                    </div>
                  </div>

                  {/* Expanded panel */}
                  {isExpanded && (
                    <div style={{ borderBottom: '1px solid var(--border)' }}>
                      {mode === 'search' && (
                        <EpisodeSearchPanel
                          results={searchResults}
                          isLoading={searchLoading}
                          onProcess={onProcess}
                        />
                      )}
                      {mode === 'history' && (
                        <EpisodeHistoryPanel
                          entries={historyEntries}
                          isLoading={historyLoading}
                        />
                      )}
                      {mode === 'tracks' && (
                        <TrackPanel
                          episodeId={ep.id}
                          onOpenEditor={onOpenEditor}
                        />
                      )}
                    </div>
                  )}
                </div>
                </EpisodeRow>
              )
            })}

          {/* Batch toolbar — shown when any episodes are selected */}
          {selectedEpisodes.size > 0 && (
            <div
              data-testid="episode-batch-toolbar"
              className="flex items-center gap-2 px-3 py-2 rounded-lg mt-2 mx-2 mb-2"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--accent-dim)',
              }}
            >
              <span className="text-xs font-medium mr-1" style={{ color: 'var(--accent)' }}>
                {selectedEpisodes.size} selected
              </span>
              <button
                onClick={() => { void startWantedBatchSearch([...selectedEpisodes]); clearAll() }}
                className="px-3 py-1 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
              >
                Search
              </button>
              <button
                onClick={() => { onExtract?.(); clearAll() }}
                disabled={isExtracting}
                className="px-3 py-1 rounded text-xs font-medium inline-flex items-center gap-1.5"
                style={{
                  backgroundColor: isExtracting ? 'var(--accent-bg)' : 'var(--bg-surface)',
                  color: isExtracting ? 'var(--accent)' : 'var(--text-secondary)',
                  border: `1px solid ${isExtracting ? 'var(--accent-dim)' : 'var(--border)'}`,
                  opacity: isExtracting ? 0.8 : 1,
                  cursor: isExtracting ? 'default' : 'pointer',
                }}
              >
                {isExtracting
                  ? <><Loader2 size={11} className="animate-spin" /> Extrahiere...</>
                  : 'Extract'}
              </button>
              <button
                onClick={() => { void batchTranslateMutation.mutate([...selectedEpisodes]); clearAll() }}
                disabled={batchTranslateMutation.isPending}
                className="px-3 py-1 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
              >
                Translate
              </button>
              <button
                onClick={() => { onOpenCleanupModal(); clearAll() }}
                className="px-3 py-1 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
              >
                Bereinigen
              </button>
              <button
                onClick={clearAll}
                className="ml-auto px-2 py-1 rounded text-xs"
                style={{ color: 'var(--text-muted)' }}
              >
                Clear
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
