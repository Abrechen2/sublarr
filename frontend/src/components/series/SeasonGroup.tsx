import { useState, useMemo, useCallback } from 'react'
import { ChevronDown, ChevronRight, Loader2, X, Eye, Pencil, Play, FileCode } from 'lucide-react'
import { EpisodeRow } from '@/components/library/EpisodeRow'
import { EpisodeActionMenu } from '@/components/episodes/EpisodeActionMenu'
import { SubBadge } from './SubBadge'
import { EpisodeSearchPanel } from './EpisodeSearchPanel'
import { EpisodeHistoryPanel } from './EpisodeHistoryPanel'
import { TrackPanel } from '@/components/tracks/TrackPanel'
import { HealthBadge } from '@/components/health/HealthBadge'
import { SubtitleActionsMenu } from '@/components/processing/SubtitleActionsMenu'
import { normLang, deriveSubtitlePath } from './seriesUtils'
import { toast } from '@/components/shared/Toast'
import { getSubtitleDownloadUrl, startWantedBatchSearch, exportSubtitleNfo } from '@/api/client'
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

export function SeasonGroup({ season, episodes, targetLanguages, seriesId: _seriesId, isExtracting, onExtract, expandedEp, onSearch, onInteractiveSearch, onHistory, onTracks, onClose, searchResults, searchLoading, historyEntries, historyLoading, onProcess, onPreviewSub, onEditSub, onCompare, onSync, onAutoSync, onVideoSync, onHealthCheck, healthScores, onOpenEditor, sidecarMap, onDeleteSidecar, onOpenCleanupModal, onPreview, streamingEnabled, onRefreshSidecars, t }: SeasonGroupProps) {
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
                    className="flex items-start transition-colors"
                    style={{
                      padding: '10px 14px',
                      borderBottom: isExpanded ? 'none' : '1px solid var(--border)',
                      backgroundColor: isExpanded ? 'var(--bg-surface-hover)' : '',
                    }}
                    onMouseEnter={(e) => {
                      if (!isExpanded) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                    }}
                    onMouseLeave={(e) => {
                      if (!isExpanded) e.currentTarget.style.backgroundColor = ''
                    }}
                  >
                    {/* Selection checkbox */}
                    <div className="w-6 flex-shrink-0 flex items-center">
                      <input
                        type="checkbox"
                        checked={selectedEpisodes.has(ep.id)}
                        onChange={() => toggleEpisode(ep.id)}
                        className="rounded"
                        style={{ accentColor: 'var(--accent)' }}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>

                    {/* Monitored indicator */}
                    <div className="w-5 flex-shrink-0">
                      {ep.has_file ? (
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: 'var(--success)' }}
                          title={t('series_detail.has_file')}
                        />
                      ) : (
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: 'var(--text-muted)' }}
                          title={t('series_detail.no_file')}
                        />
                      )}
                    </div>

                    {/* Episode number */}
                    <div
                      className="w-12 flex-shrink-0 text-sm font-medium"
                      style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                    >
                      {ep.episode}
                    </div>

                    {/* Title */}
                    <div className="flex-1 min-w-0 text-sm truncate" title={ep.title}>
                      {ep.title || t('series_detail.tba')}
                    </div>

                    {/* Audio */}
                    <div className="w-24 flex-shrink-0 flex gap-1">
                      {ep.audio_languages.length > 0 ? (
                        ep.audio_languages.map((lang, i) => (
                          <span
                            key={i}
                            className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase"
                            style={{
                              backgroundColor: 'rgba(99, 102, 241, 0.12)',
                              color: '#818cf8',
                            }}
                          >
                            {lang}
                          </span>
                        ))
                      ) : (
                        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>&mdash;</span>
                      )}
                    </div>

                    {/* Subtitles */}
                    <div className="flex-1 min-w-[200px] flex gap-1 flex-wrap items-center">
                      {ep.has_file ? (
                        <>
                          {/* Target language badges: teal=ass, amber=srt, orange=missing */}
                          {targetLanguages.length > 0 ? targetLanguages.map((lang) => {
                            const subFormat = ep.subtitles[lang] || ''
                            const epSidecars = sidecarMap[String(ep.id)] ?? []
                            // Find matching sidecar on disk (handles ISO 639-2 ↔ 639-1 mismatch)
                            const matchingSidecar = (subFormat === 'ass' || subFormat === 'srt')
                              ? epSidecars.find(s => normLang(s.language) === normLang(lang) && s.format === subFormat)
                              : null
                            return (
                              <span key={lang} className="inline-flex items-center gap-0.5">
                                <SubBadge lang={lang} format={subFormat} />
                                {matchingSidecar && (
                                  <>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); void onDeleteSidecar(matchingSidecar.path) }}
                                      className="p-0.5 rounded hover:opacity-80"
                                      style={{ color: 'var(--error)', lineHeight: 1 }}
                                      title={`Löschen: ${matchingSidecar.path}`}
                                    >
                                      <X size={9} />
                                    </button>
                                    <a
                                      href={getSubtitleDownloadUrl(matchingSidecar.path)}
                                      download
                                      title={`Download ${matchingSidecar.language} ${matchingSidecar.format}`}
                                      className="ml-1 text-neutral-400 hover:text-teal-400 transition-colors"
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      <svg
                                        xmlns="http://www.w3.org/2000/svg"
                                        className="h-3.5 w-3.5 inline"
                                        viewBox="0 0 20 20"
                                        fill="currentColor"
                                        aria-hidden="true"
                                      >
                                        <path
                                          fillRule="evenodd"
                                          d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
                                          clipRule="evenodd"
                                        />
                                      </svg>
                                    </a>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); exportSubtitleNfo(matchingSidecar.path).then(() => toast('NFO exported', 'success')).catch(() => toast('NFO export failed', 'error')) }}
                                      className="p-0.5 rounded transition-colors"
                                      style={{ color: 'var(--text-muted)', lineHeight: 1 }}
                                      title="Export NFO sidecar"
                                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
                                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
                                    >
                                      <FileCode size={11} />
                                    </button>
                                    <SubtitleActionsMenu
                                      subtitlePath={matchingSidecar.path}
                                      onRefresh={onRefreshSidecars}
                                    />
                                  </>
                                )}
                                {(subFormat === 'ass' || subFormat === 'srt') && (
                                  <>
                                    <HealthBadge score={healthScores[deriveSubtitlePath(ep.file_path, lang, subFormat)] ?? null} size="sm" />
                                    <button
                                      onClick={() => onPreviewSub(deriveSubtitlePath(ep.file_path, lang, subFormat))}
                                      className="p-0.5 rounded transition-colors"
                                      style={{ color: 'var(--text-muted)' }}
                                      title="Preview subtitle"
                                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
                                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
                                    >
                                      <Eye size={12} />
                                    </button>
                                    <button
                                      onClick={() => onEditSub(deriveSubtitlePath(ep.file_path, lang, subFormat))}
                                      className="p-0.5 rounded transition-colors"
                                      style={{ color: 'var(--text-muted)' }}
                                      title="Edit subtitle"
                                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
                                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
                                    >
                                      <Pencil size={12} />
                                    </button>
                                  </>
                                )}
                              </span>
                            )
                          }) : (
                            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>&#x2014;</span>
                          )}

                          {/* Extra sidecar badges: non-target languages, deduped via normLang */}
                          {(() => {
                            const epSidecars = sidecarMap[String(ep.id)] ?? []
                            const extraSidecars = epSidecars.filter(
                              s => !targetLanguages.some(tl => normLang(tl) === normLang(s.language))
                            )
                            if (extraSidecars.length === 0) return null
                            return extraSidecars.map((s) => (
                              <span
                                key={s.path}
                                className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase"
                                style={{
                                  backgroundColor: 'var(--bg-surface)',
                                  color: 'var(--text-muted)',
                                  border: '1px solid var(--border)',
                                }}
                                title={`${s.language.toUpperCase()} ${s.format.toUpperCase()} — extra sidecar`}
                              >
                                {s.language.toUpperCase()}
                                <span style={{ opacity: 0.6, fontSize: '9px' }}>{s.format}</span>
                                <button
                                  onClick={(e) => { e.stopPropagation(); void onDeleteSidecar(s.path) }}
                                  className="ml-0.5 rounded hover:opacity-80"
                                  style={{ color: 'var(--error)', lineHeight: 1 }}
                                  title={`Löschen: ${s.path}`}
                                >
                                  <X size={9} />
                                </button>
                                <a
                                  href={getSubtitleDownloadUrl(s.path)}
                                  download
                                  title={`Download ${s.language} ${s.format}`}
                                  className="ml-1 text-neutral-400 hover:text-teal-400 transition-colors"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <svg
                                    xmlns="http://www.w3.org/2000/svg"
                                    className="h-3.5 w-3.5 inline"
                                    viewBox="0 0 20 20"
                                    fill="currentColor"
                                    aria-hidden="true"
                                  >
                                    <path
                                      fillRule="evenodd"
                                      d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
                                      clipRule="evenodd"
                                    />
                                  </svg>
                                </a>
                                <SubtitleActionsMenu
                                  subtitlePath={s.path}
                                  onRefresh={onRefreshSidecars}
                                />
                              </span>
                            ))
                          })()}
                        </>
                      ) : (
                        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>No file</span>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="w-64 flex-shrink-0 flex gap-0.5 justify-end">
                      {streamingEnabled && ep.has_file && ep.file_path && (
                        <button
                          onClick={() => onPreview(ep)}
                          className="hover-surface p-1 rounded text-[var(--text-muted)] hover:text-[var(--teal-accent)]"
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
