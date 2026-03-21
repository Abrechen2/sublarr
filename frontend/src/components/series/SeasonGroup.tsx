import { useState } from 'react'
import type React from 'react'
import { ChevronDown, ChevronRight, Mic, Tv2 } from 'lucide-react'
import { getRowStatus } from '@/components/library/EpisodeRow'
import { EpisodeSearchPanel } from './EpisodeSearchPanel'
import { EpisodeHistoryPanel } from './EpisodeHistoryPanel'
import { TrackPanel } from '@/components/tracks/TrackPanel'
import { episodeGridRowStyle, FormatBadge, ScoreCell, ProviderCell, EpisodeInlineActions } from './EpisodeGrid'
import { deriveSubtitlePath } from './seriesUtils'
import type { EpisodeInfo, WantedSearchResponse, EpisodeHistoryEntry, SidecarSubtitle } from '@/lib/types'
import { useTranscribeEpisode, useDetectOpeningEnding } from '@/hooks/useTranslationApi'

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

export function SeasonGroup({ season, episodes, targetLanguages, seriesId: _seriesId, isExtracting: _isExtracting, onExtract: _onExtract, expandedEp, onSearch, onInteractiveSearch, onHistory: _onHistory, onTracks: _onTracks, onClose: _onClose, searchResults, searchLoading, historyEntries, historyLoading, onProcess, onPreviewSub: _onPreviewSub, onEditSub: _onEditSub, onCompare: _onCompare, onSync: _onSync, onAutoSync, onVideoSync: _onVideoSync, onHealthCheck: _onHealthCheck, healthScores: _healthScores, onOpenEditor, sidecarMap: _sidecarMap, onDeleteSidecar, onOpenCleanupModal: _onOpenCleanupModal, onPreview: _onPreview, streamingEnabled: _streamingEnabled, onRefreshSidecars: _onRefreshSidecars, t }: SeasonGroupProps) {
  const [expanded, setExpanded] = useState(true)
  const transcribe = useTranscribeEpisode()
  const detectOpEd = useDetectOpeningEnding()

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
      </div>

      {/* Episodes */}
      {expanded && (
        <div>
          {episodes
            .sort((a, b) => a.episode - b.episode)
            .map((ep) => {
              const isExpanded = expandedEp?.id === ep.id
              const mode = expandedEp?.mode

              // Derive status
              const status = getRowStatus(ep, targetLanguages)
              const isSearching = false // TODO: derive from wanted_items status once exposed

              // Primary score/provider (first target language)
              const firstLang = targetLanguages[0] ?? ''
              const score = ep.subtitle_scores?.[firstLang] ?? null
              const provider = ep.subtitle_providers?.[firstLang] ?? null

              // Subtitle status text (file subtitle line)
              const filename = ep.has_file
                ? ep.file_path.split(/[/\\]/).pop() ?? ep.file_path
                : null

              const epNumberColor =
                status === 'missing' ? 'var(--error)' :
                status === 'low-score' ? 'var(--warning)' :
                'var(--text-secondary)'

              const statusBorderOverride: React.CSSProperties =
                status === 'missing'
                  ? { borderColor: 'var(--error)', borderLeft: '2px solid var(--error)' }
                  : status === 'low-score'
                  ? { borderColor: 'var(--warning)', borderLeft: '2px solid var(--warning)' }
                  : {}

              return (
                <div key={ep.id} data-testid="episode-row">
                  <div
                    style={{ ...episodeGridRowStyle({ status, isExpanded }), ...statusBorderOverride }}
                    onMouseEnter={(e) => {
                      if (!isExpanded) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                    }}
                    onMouseLeave={(e) => {
                      if (!isExpanded) e.currentTarget.style.backgroundColor = 'var(--bg-surface)'
                    }}
                  >
                    {/* Column 1: EP number */}
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600, color: epNumberColor }}>
                      E{String(ep.episode).padStart(2, '0')}
                    </div>

                    {/* Column 2: Title + file/status line */}
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '13px', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {ep.title || 'TBA'}
                      </div>
                      <div style={{ fontSize: '11px', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {isSearching ? (
                          <span style={{ color: 'var(--error)' }}>Searching…</span>
                        ) : status === 'missing' ? (
                          <span style={{ color: 'var(--error)' }}>No subtitle found</span>
                        ) : filename ? (
                          <span style={{ color: 'var(--text-muted)' }}>{filename}</span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>No file</span>
                        )}
                      </div>
                    </div>

                    {/* Column 3: Format */}
                    <FormatBadge format={ep.has_file ? (ep.subtitles[firstLang] ?? '') : ''} />

                    {/* Column 4: Provider */}
                    <ProviderCell provider={status === 'missing' ? null : provider} />

                    {/* Column 5: Score */}
                    <ScoreCell status={status} score={score} isSearching={isSearching} />

                    {/* Column 6: Inline actions */}
                    <EpisodeInlineActions
                      status={status}
                      isSearching={isSearching}
                      onSearch={() => onSearch(ep)}
                      onSkip={() => { /* TODO: implement skip */ }}
                      onFindBetter={() => onSearch(ep)}
                      onAccept={() => { /* TODO: implement accept */ }}
                      onSync={() => {
                        const path = deriveSubtitlePath(ep.file_path, firstLang, ep.subtitles[firstLang] ?? '')
                        if (path) onAutoSync(path, ep.file_path)
                      }}
                      onDelete={() => {
                        const path = deriveSubtitlePath(ep.file_path, firstLang, ep.subtitles[firstLang] ?? '')
                        if (path) void onDeleteSidecar(path)
                      }}
                      onMore={() => onInteractiveSearch(ep)}
                    />
                    {/* Transcribe + OP/ED detect buttons (only when episode has a file) */}
                    {ep.has_file && (
                      <div className="flex items-center gap-1">
                        <button
                          className="p-1 rounded transition-colors"
                          title="Transcribe audio to subtitles via Whisper"
                          onClick={() => transcribe.mutate({ filePath: ep.file_path })}
                          disabled={transcribe.isPending}
                          data-testid={`transcribe-btn-${ep.id}`}
                          style={{ color: 'var(--text-muted)' }}
                          onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                        >
                          <Mic size={13} />
                        </button>
                        <button
                          className="p-1 rounded transition-colors"
                          title="Detect OP/ED segments"
                          onClick={() => detectOpEd.mutate(ep.file_path)}
                          disabled={detectOpEd.isPending}
                          data-testid={`detect-oped-btn-${ep.id}`}
                          style={{ color: 'var(--text-muted)' }}
                          onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                        >
                          <Tv2 size={13} />
                        </button>
                      </div>
                    )}
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
              )
            })}
        </div>
      )}
    </div>
  )
}
