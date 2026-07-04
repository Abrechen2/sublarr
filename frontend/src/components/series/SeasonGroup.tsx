import { useState, useMemo, useCallback, Fragment } from 'react'
import { ChevronDown, ChevronRight, Play, X, Download, Loader2 } from 'lucide-react'
import { getRowStatus } from '@/components/library/EpisodeRow'
import { EpisodeSearchPanel } from './EpisodeSearchPanel'
import { EpisodeHistoryPanel } from './EpisodeHistoryPanel'
import { TrackPanel } from '@/components/tracks/TrackPanel'
import { EPISODE_GRID_COLUMNS } from './EpisodeGrid'
import { normLang, deriveSubtitlePath } from './seriesUtils'
import { HealthBadge } from '@/components/health/HealthBadge'
import { EpisodeActionMenu } from '@/components/episodes/EpisodeActionMenu'
import { SubtitleActionsMenu } from '@/components/processing/SubtitleActionsMenu'
import { useBatchTranslate } from '@/hooks/useTranslationApi'
import { startWantedBatchSearch, getSubtitleDownloadUrl } from '@/api/client'
import { useTranscribeEpisode, useDetectOpeningEnding } from '@/hooks/useTranslationApi'
import { Mic, Tv2 } from 'lucide-react'
import type { EpisodeInfo, WantedSearchResponse, EpisodeHistoryEntry, SidecarSubtitle } from '@/lib/types'

// ─── SubBadge ─────────────────────────────────────────────────────────────────

function SubBadge({ lang, format }: { lang: string; format: string }) {
  const isOptimal = format === 'ass' || format === 'embedded_ass'
  const isUpgradeable = format === 'srt' || format === 'embedded_srt'
  const isEmbedded = format === 'embedded_ass' || format === 'embedded_srt'
  const hasFile = isOptimal || isUpgradeable

  const bg = isOptimal
    ? 'var(--accent-bg)'
    : isUpgradeable
    ? 'var(--upgrade-bg, rgba(167,139,250,0.12))'
    : 'var(--warning-bg, rgba(245,158,11,0.12))'
  const color = isOptimal
    ? 'var(--accent)'
    : isUpgradeable
    ? 'var(--upgrade, #a78bfa)'
    : 'var(--warning, #f59e0b)'
  const border = isOptimal
    ? '1px solid var(--accent-dim)'
    : isUpgradeable
    ? '1px solid rgba(167,139,250,0.4)'
    : '1px solid rgba(245,158,11,0.3)'
  const label = isEmbedded ? format.replace('embedded_', '') + '⊕' : format
  const title = hasFile
    ? `${lang.toUpperCase()} (${format.toUpperCase()}${isEmbedded ? ' — embedded' : ''}${isUpgradeable ? ' — upgradeable to ASS' : ''})`
    : `${lang.toUpperCase()} missing`

  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide"
      style={{ backgroundColor: bg, color, border }}
      title={title}
    >
      {lang.toUpperCase()}
      {hasFile && <span style={{ opacity: 0.6, fontSize: '9px' }}>{label}</span>}
    </span>
  )
}

// ─── SeasonGroupProps ─────────────────────────────────────────────────────────

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
  readonly onPreviewSub: (filePath: string, videoPath: string) => void
  readonly onEditSub: (filePath: string, videoPath: string) => void
  readonly onCompare: (ep: EpisodeInfo) => void
  readonly onCombine: (ep: EpisodeInfo) => void
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
  // Plan 4: skip/accept wiring
  readonly episodeWantedMap?: Map<number, number>
  readonly onSkipEpisode?: (episodeId: number) => void
  readonly onAcceptEpisode?: (episodeId: number) => void
}

// ─── SeasonGroup ──────────────────────────────────────────────────────────────

export function SeasonGroup({
  season, episodes, targetLanguages, seriesId: _seriesId,
  isExtracting, onExtract, expandedEp,
  onSearch, onInteractiveSearch, onHistory: _onHistory, onTracks: _onTracks, onClose,
  searchResults, searchLoading, historyEntries, historyLoading,
  onProcess, onPreviewSub, onEditSub, onCompare, onCombine, onSync, onAutoSync, onVideoSync,
  onHealthCheck, healthScores, onOpenEditor, sidecarMap, onDeleteSidecar,
  onOpenCleanupModal, onPreview, streamingEnabled, onRefreshSidecars, t,
  episodeWantedMap: _episodeWantedMap, onSkipEpisode, onAcceptEpisode,
}: SeasonGroupProps) {
  const [expanded, setExpanded] = useState(true)
  const [selectedEpisodes, setSelectedEpisodes] = useState<Set<number>>(new Set())
  const batchTranslateMutation = useBatchTranslate()
  const transcribe = useTranscribeEpisode()
  const detectOpEd = useDetectOpeningEnding()

  const allSelectableIds = useMemo(
    () => episodes.map((e) => e.id).filter((id): id is number => id != null),
    [episodes]
  )

  const toggleEpisode = useCallback((id: number) => {
    setSelectedEpisodes((prev) => {
      const next = new Set(prev)
      if (next.has(id)) { next.delete(id) } else { next.add(id) }
      return next
    })
  }, [])

  const selectAll = useCallback(() => setSelectedEpisodes(new Set(allSelectableIds)), [allSelectableIds])
  const clearAll = useCallback(() => setSelectedEpisodes(new Set()), [])

  return (
    <div>
      {/* Season Header */}
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
              style={{ accentColor: 'var(--accent)' }}
              title={t('episode_ui.season_select_all')}
            />
            <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{t('episode_ui.select_all_short')}</span>
          </div>
        )}
      </div>

      {/* Episodes */}
      {expanded && (
        <div>
          {episodes
            .sort((a, b) => a.episode - b.episode)
            .map((ep) => {
              const isExpanded = expandedEp?.id === ep.id
              const mode = expandedEp?.mode

              const status = getRowStatus(ep, targetLanguages)
              const firstLang = targetLanguages[0] ?? ''

              const epNumberColor =
                status === 'missing' ? 'var(--error)' :
                status === 'low-score' ? 'var(--warning)' :
                'var(--text-secondary)'

              // hasMultipleSubs gates the Compare entry in EpisodeActionMenu.
              const hasMultipleSubs = ep.has_file
                ? Object.values(ep.subtitles).filter((f) => f === 'ass' || f === 'srt').length >= 2
                : false

              // Suppress unused variable warning
              void firstLang

              return (
                <div key={ep.id} data-testid="episode-row">
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: EPISODE_GRID_COLUMNS,
                      alignItems: 'center',
                      gap: '10px',
                      padding: '6px 14px',
                      borderBottom: isExpanded ? 'none' : '1px solid var(--border)',
                      backgroundColor: isExpanded ? 'var(--bg-surface-hover)' : 'var(--bg-surface)',
                      ...(status === 'missing' ? { borderLeft: '2px solid var(--error)' } :
                         status === 'low-score' ? { borderLeft: '2px solid var(--warning)' } : {}),
                    }}
                    onMouseEnter={(e) => {
                      if (!isExpanded) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                    }}
                    onMouseLeave={(e) => {
                      if (!isExpanded) e.currentTarget.style.backgroundColor = 'var(--bg-surface)'
                    }}
                  >
                    {/* Col 1: Checkbox */}
                    <input
                      type="checkbox"
                      checked={selectedEpisodes.has(ep.id)}
                      onChange={() => toggleEpisode(ep.id)}
                      onClick={(e) => e.stopPropagation()}
                      style={{ accentColor: 'var(--accent)' }}
                    />

                    {/* Col 2: EP number */}
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600, color: epNumberColor }}>
                      E{String(ep.episode).padStart(2, '0')}
                    </div>

                    {/* Col 3: Title + file line */}
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '13px', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {ep.title || t('episode_ui.tba')}
                      </div>
                      <div style={{ fontSize: '11px', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {status === 'missing' ? (
                          <span style={{ color: 'var(--error)' }}>{t('episode_ui.no_subtitle_found')}</span>
                        ) : ep.file_path ? (
                          <span style={{ color: 'var(--text-muted)' }}>
                            {ep.file_path.split(/[/\\]/).pop() ?? ep.file_path}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>{t('episode_ui.no_file')}</span>
                        )}
                      </div>
                    </div>

                    {/* Col 4: Audio language badges */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px' }}>
                      {ep.audio_languages && ep.audio_languages.length > 0 ? (
                        ep.audio_languages.map((lang, i) => (
                          <span
                            key={i}
                            className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase"
                            style={{ backgroundColor: 'rgba(99,102,241,0.12)', color: '#818cf8' }}
                          >
                            {lang}
                          </span>
                        ))
                      ) : (
                        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>—</span>
                      )}
                    </div>

                    {/* Col 5: Subtitle badges + sidecar actions */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', alignItems: 'center' }}>
                      {ep.has_file ? (
                        <>
                          {targetLanguages.length > 0 ? targetLanguages.map((lang) => {
                            const subFormat = ep.subtitles[lang] || ''
                            const epSidecars = sidecarMap[String(ep.id)] ?? []
                            // Prefer the unmodified sidecar (no .hi/.forced/.sdh/.cc) over modifier
                            // variants — the active subtitle for the language is always the plain one.
                            const matchingSidecar = (subFormat === 'ass' || subFormat === 'srt')
                              ? (() => {
                                  const candidates = epSidecars.filter(
                                    (s) => normLang(s.language) === normLang(lang) && s.format === subFormat,
                                  )
                                  return candidates.find((s) => !s.modifier) ?? candidates[0] ?? null
                                })()
                              : null
                            // Modifier siblings (same lang+format, with .hi/.forced/.sdh/.cc) shown
                            // alongside the primary so the user can see HI/forced variants exist.
                            const modifierSiblings = (subFormat === 'ass' || subFormat === 'srt')
                              ? epSidecars.filter(
                                  (s) =>
                                    normLang(s.language) === normLang(lang) &&
                                    s.format === subFormat &&
                                    s.modifier &&
                                    s.path !== matchingSidecar?.path,
                                )
                              : []
                            const subPath = (subFormat === 'ass' || subFormat === 'srt')
                              ? deriveSubtitlePath(ep.file_path, lang, subFormat)
                              : null
                            return (
                              <Fragment key={lang}>
                              <span className="inline-flex items-center gap-0.5">
                                <SubBadge lang={lang} format={subFormat} />
                                {subPath && (
                                  <HealthBadge score={healthScores[subPath] ?? null} size="sm" />
                                )}
                                {matchingSidecar && (
                                  <>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); void onDeleteSidecar(matchingSidecar.path) }}
                                      className="p-0.5 rounded hover:opacity-80"
                                      style={{ color: 'var(--error)', lineHeight: 1 }}
                                      title={t('episode_ui.delete_path', { path: matchingSidecar.path })}
                                    >
                                      <X size={9} />
                                    </button>
                                    <SubtitleActionsMenu
                                      subtitlePath={matchingSidecar.path}
                                      onRefresh={onRefreshSidecars}
                                      onPreview={(p) => onPreviewSub(p, ep.file_path)}
                                      onEdit={(p) => onEditSub(p, ep.file_path)}
                                      onSync={onSync}
                                      onAutoSync={(p) => onAutoSync(p, ep.file_path)}
                                      onVideoSync={(p) => onVideoSync(ep, p)}
                                      onHealthCheck={onHealthCheck}
                                    />
                                  </>
                                )}
                              </span>
                              {modifierSiblings.map((sib) => (
                                <span
                                  key={sib.path}
                                  className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase"
                                  style={{
                                    backgroundColor: 'var(--warning-bg, #5a3d10)',
                                    color: 'var(--warning, #ffb84d)',
                                    border: '1px solid var(--warning, #ffb84d)',
                                  }}
                                  title={t('episode_ui.variant_title', { lang: sib.language.toUpperCase(), modifier: (sib.modifier ?? '').toUpperCase(), path: sib.path })}
                                >
                                  {sib.language.toUpperCase()}
                                  <span style={{ opacity: 0.85 }}>{(sib.modifier ?? '').toUpperCase()}</span>
                                  <button
                                    onClick={(e) => { e.stopPropagation(); void onDeleteSidecar(sib.path) }}
                                    className="ml-0.5 rounded hover:opacity-80"
                                    style={{ color: 'var(--error)', lineHeight: 1 }}
                                    title={t('episode_ui.delete_path', { path: sib.path })}
                                  >
                                    <X size={9} />
                                  </button>
                                  <a
                                    href={getSubtitleDownloadUrl(sib.path)}
                                    download
                                    title={t('episode_ui.download_variant_title', { lang: sib.language, modifier: sib.modifier, format: sib.format })}
                                    className="p-0.5"
                                    style={{ color: 'inherit', lineHeight: 1 }}
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <Download size={10} />
                                  </a>
                                  <SubtitleActionsMenu subtitlePath={sib.path} onRefresh={onRefreshSidecars} />
                                </span>
                              ))}
                              </Fragment>
                            )
                          }) : <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>—</span>}

                          {/* Extra sidecars (non-target langs) */}
                          {(() => {
                            const epSidecars = sidecarMap[String(ep.id)] ?? []
                            const extras = epSidecars.filter(
                              (s) => !targetLanguages.some((tl) => normLang(tl) === normLang(s.language))
                            )
                            return extras.map((s) => (
                              <span
                                key={s.path}
                                className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase"
                                style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}
                                title={t('episode_ui.extra_sidecar_title', { lang: `${s.language.toUpperCase()}${s.modifier ? ' ' + s.modifier.toUpperCase() : ''} ${s.format.toUpperCase()}` })}
                              >
                                {s.language.toUpperCase()}
                                {s.modifier && (
                                  <span style={{ color: 'var(--warning, #ffb84d)', fontWeight: 700 }}>
                                    {s.modifier.toUpperCase()}
                                  </span>
                                )}
                                <span style={{ opacity: 0.6, fontSize: '9px' }}>{s.format}</span>
                                <button
                                  onClick={(e) => { e.stopPropagation(); void onDeleteSidecar(s.path) }}
                                  className="ml-0.5 rounded hover:opacity-80"
                                  style={{ color: 'var(--error)', lineHeight: 1 }}
                                  title={t('episode_ui.delete_path', { path: s.path })}
                                >
                                  <X size={9} />
                                </button>
                                <a
                                  href={getSubtitleDownloadUrl(s.path)}
                                  download
                                  title={t('episode_ui.download_title', { lang: s.language, format: s.format })}
                                  className="p-0.5"
                                  style={{ color: 'var(--text-muted)', lineHeight: 1 }}
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <Download size={10} />
                                </a>
                                <SubtitleActionsMenu subtitlePath={s.path} onRefresh={onRefreshSidecars} />
                              </span>
                            ))
                          })()}
                        </>
                      ) : (
                        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{t('episode_ui.no_file')}</span>
                      )}
                    </div>

                    {/* Col 6: Actions */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '2px' }}>
                      {/* Play button (streaming) */}
                      {streamingEnabled && ep.has_file && ep.file_path && (
                        <button
                          onClick={() => onPreview(ep)}
                          className="p-1 rounded transition-colors"
                          style={{ color: 'var(--text-muted)' }}
                          title={t('episode_ui.preview_in_player')}
                          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
                          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
                        >
                          <Play size={13} />
                        </button>
                      )}
                      {/* Transcribe button */}
                      {ep.has_file && (
                        <>
                          <button
                            className="p-1 rounded transition-colors"
                            title={t('episode_ui.transcribe_whisper')}
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
                            title={t('episode_ui.detect_op_ed')}
                            onClick={() => detectOpEd.mutate(ep.file_path)}
                            disabled={detectOpEd.isPending}
                            data-testid={`detect-oped-btn-${ep.id}`}
                            style={{ color: 'var(--text-muted)' }}
                            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                            onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                          >
                            <Tv2 size={13} />
                          </button>
                        </>
                      )}
                      {/* Skip (for missing episodes) */}
                      {status === 'missing' && onSkipEpisode && (
                        <button
                          onClick={() => onSkipEpisode(ep.id)}
                          style={{
                            fontSize: '11px', padding: '3px 8px', borderRadius: '4px',
                            backgroundColor: 'transparent', color: 'var(--text-secondary)',
                            border: '1px solid var(--border)', cursor: 'pointer',
                          }}
                          title={t('episode_ui.skip_ignored')}
                        >
                          {t('episode_ui.skip')}
                        </button>
                      )}
                      {/* Accept (for low-score episodes) */}
                      {status === 'low-score' && onAcceptEpisode && (
                        <button
                          onClick={() => onAcceptEpisode(ep.id)}
                          style={{
                            fontSize: '11px', padding: '3px 8px', borderRadius: '4px',
                            backgroundColor: 'transparent', color: 'var(--text-secondary)',
                            border: '1px solid var(--border)', cursor: 'pointer',
                          }}
                          title={t('episode_ui.accept_quality')}
                        >
                          {t('episode_ui.accept')}
                        </button>
                      )}
                      {/* Full action menu */}
                      <EpisodeActionMenu
                        ep={ep}
                        isExpanded={isExpanded}
                        mode={mode}
                        searchLoading={searchLoading}
                        historyLoading={historyLoading}
                        hasMultipleSubs={hasMultipleSubs}
                        onSearch={() => onSearch(ep)}
                        onCompare={() => onCompare(ep)}
                        onCombine={() => onCombine(ep)}
                        onTracks={() => _onTracks(ep)}
                        onInteractiveSearch={() => onInteractiveSearch(ep)}
                        onHistory={() => _onHistory(ep)}
                        onClose={onClose}
                      />
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
              )
            })}

          {/* Batch toolbar */}
          {selectedEpisodes.size > 0 && (
            <div
              data-testid="episode-batch-toolbar"
              className="flex items-center gap-2 px-3 py-2 rounded-lg mt-2 mx-2 mb-2"
              style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--accent-dim)' }}
            >
              <span className="text-xs font-medium mr-1" style={{ color: 'var(--accent)' }}>
                {t('episode_ui.selected_count', { count: selectedEpisodes.size })}
              </span>
              <button
                onClick={() => { void startWantedBatchSearch([...selectedEpisodes]); clearAll() }}
                className="px-3 py-1 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
              >
                {t('episode_ui.search')}
              </button>
              <button
                onClick={() => { onExtract?.(); clearAll() }}
                disabled={isExtracting}
                className="px-3 py-1 rounded text-xs font-medium inline-flex items-center gap-1.5 disabled:opacity-60"
                style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
              >
                {isExtracting ? <Loader2 size={11} className="animate-spin" /> : null}
                {t('episode_ui.extract')}
              </button>
              <button
                onClick={() => {
                  void batchTranslateMutation.mutate([...selectedEpisodes])
                  clearAll()
                }}
                disabled={batchTranslateMutation.isPending}
                className="px-3 py-1 rounded text-xs font-medium disabled:opacity-60"
                style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
              >
                {t('episode_ui.translate')}
              </button>
              <button
                onClick={() => { onOpenCleanupModal(); clearAll() }}
                className="px-3 py-1 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
              >
                {t('episode_ui.cleanup')}
              </button>
              <button
                onClick={clearAll}
                className="ml-auto px-2 py-1 rounded text-xs"
                style={{ color: 'var(--text-muted)' }}
              >
                {t('episode_ui.clear')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
