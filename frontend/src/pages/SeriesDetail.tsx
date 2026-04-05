import { useState, useMemo, useCallback, lazy, Suspense, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { SeasonSummaryBar } from '@/components/library/SeasonSummaryBar'
import { useSeriesDetail, useEpisodeSearch, useEpisodeHistory, useProcessWantedItem, useStartWantedBatch, useUpdateSeriesSettings, useRefreshAnidbMapping, useStreamingEnabled, useSeriesFansubPrefs, useRescanSeries } from '@/hooks/useApi'
import { useWantedItems, useUpdateWantedStatus } from '@/hooks/useWantedApi'
import {
  ArrowLeft, Loader2,
  X, Trash2,
} from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import SubtitleEditorModal from '@/components/editor/SubtitleEditorModal'
import { PlayerModal } from '@/components/player/PlayerModal'
import type { PlayerSubtitleTrack } from '@/lib/types'
import { autoSyncFile, batchExtractAllTracks, listSeriesSubtitles, deleteSubtitles, getSeriesSubtitleExportUrl, exportSeriesNfo } from '@/api/client'
import { useWebSocket } from '@/hooks/useWebSocket'
import { ProgressBar } from '@/components/shared/ProgressBar'
import { InteractiveSearchModal } from '@/components/wanted/InteractiveSearchModal'
import { ComparisonSelector } from '@/components/comparison/ComparisonSelector'
import { SubtitleCleanupModal } from '@/components/shared/SubtitleCleanupModal'
import type { EpisodeInfo, WantedSearchResponse, EpisodeHistoryEntry, SidecarSubtitle } from '@/lib/types'
import { FansubOverrideModal } from '@/components/series/FansubOverrideModal'
import { deriveSubtitlePath } from '@/components/series/seriesUtils'

import { GlossaryPanel } from '@/components/series/GlossaryPanel'
import { SeasonGroup } from '@/components/series/SeasonGroup'
import { EpisodeGridHeader } from '@/components/series/EpisodeGrid'
import { SeriesHero } from '@/components/series/SeriesHero'
import { SeriesSettingsPanel } from '@/components/series/SeriesSettingsPanel'
import { SeasonTabs } from '@/components/series/SeasonTabs'

const SubtitleComparison = lazy(() => import('@/components/comparison/SubtitleComparison').then(m => ({ default: m.SubtitleComparison })))
const SyncControls = lazy(() => import('@/components/sync/SyncControls').then(m => ({ default: m.SyncControls })))
const SyncModal = lazy(() => import('@/components/sync/SyncModal').then(m => ({ default: m.SyncModal })))
const HealthCheckPanel = lazy(() => import('@/components/health/HealthCheckPanel').then(m => ({ default: m.HealthCheckPanel })))

// ─── Main Page ─────────────────────────────────────────────────────────────

export function SeriesDetailPage() {
  const { t } = useTranslation('library')
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  // Fix 5: guard against malformed route parameter producing NaN
  const seriesId = id && !isNaN(Number(id)) ? Number(id) : null
  const { data: series, isLoading, error } = useSeriesDetail(seriesId)

  // Plan 4: fetch wanted items for skip/accept wiring — filter server-side by series_id
  const { data: seriesWanted } = useWantedItems(
    1, 200, 'episode', undefined, undefined, false, undefined, seriesId ?? undefined
  )
  const updateWantedStatus = useUpdateWantedStatus()

  const episodeWantedMap = useMemo((): Map<number, number> => {
    const map = new Map<number, number>()
    if (!seriesWanted?.data) return map
    for (const item of seriesWanted.data) {
      if (item.sonarr_episode_id != null) {
        map.set(item.sonarr_episode_id, item.id)
      }
    }
    return map
  }, [seriesWanted?.data])

  // Episode action state
  const [expandedEp, setExpandedEp] = useState<{ id: number; mode: 'search' | 'history' | 'glossary' | 'tracks' } | null>(null)
  const [showGlossary, setShowGlossary] = useState(false)
  const [searchResults, setSearchResults] = useState<Record<number, WantedSearchResponse>>({})
  const [historyEntries, setHistoryEntries] = useState<Record<number, EpisodeHistoryEntry[]>>({})

  // Subtitle editor modal state
  const [editorFilePath, setEditorFilePath] = useState<string | null>(null)
  const [editorMode, setEditorMode] = useState<'preview' | 'edit'>('preview')

  // Web player state
  const { data: streamingEnabled } = useStreamingEnabled()
  const seekFnRef = useRef<((seconds: number) => void) | null>(null)
  const [playerState, setPlayerState] = useState<{
    videoPath: string
    tracks: PlayerSubtitleTrack[]
  } | null>(null)

  // Extraction progress (driven by WebSocket batch_extract_progress events)
  const [extractProgress, setExtractProgress] = useState<{
    current: number
    total: number
    filename: string
  } | null>(null)
  // Sidecar management
  const [showCleanupModal, setShowCleanupModal] = useState(false)
  const [fansubOpen, setFansubOpen] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const [deleteAlsoBlacklist, setDeleteAlsoBlacklist] = useState(false)
  const queryClient = useQueryClient()
  const { data: sidecarData } = useQuery({
    queryKey: ['series-subtitles', seriesId],
    queryFn: () => seriesId != null ? listSeriesSubtitles(seriesId) : Promise.resolve({ subtitles: {} }),
    enabled: seriesId != null,
    staleTime: extractProgress !== null ? 0 : 30_000,
    // Fallback poll while extraction is running (covers edge cases like reconnects)
    refetchInterval: extractProgress !== null ? 2_000 : false,
  })
  const sidecarMap: Record<string, SidecarSubtitle[]> = useMemo(() => sidecarData?.subtitles ?? {}, [sidecarData])

  // WebSocket: batch extraction progress
  useWebSocket({
    onBatchExtractProgress: (data) => {
      const d = data as { series_id: number; current: number; total: number; filename: string; status: string }
      if (d.series_id !== seriesId) return
      setExtractProgress({ current: d.current, total: d.total, filename: d.filename })
      if (d.status === 'ok') {
        void queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })
      }
    },
    onBatchExtractCompleted: (data) => {
      const d = data as { series_id: number; succeeded: number; failed: number; skipped: number }
      if (d.series_id !== seriesId) return
      if (extractTimeoutRef.current) clearTimeout(extractTimeoutRef.current)
      setExtractProgress(null)
      void queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })
      void queryClient.invalidateQueries({ queryKey: ['series', seriesId] })
      const msg = d.succeeded > 0
        ? `${d.succeeded} Track(s) extrahiert${d.failed > 0 ? `, ${d.failed} fehlgeschlagen` : ''}`
        : d.failed > 0
          ? `Extraktion fehlgeschlagen (${d.failed} Fehler)`
          : 'Extraktion abgeschlossen — alle bereits vorhanden'
      toast(msg, d.failed > 0 ? 'error' : 'success')
    },
  })

  // Comparison and sync state
  const [comparisonPaths, setComparisonPaths] = useState<string[] | null>(null)
  const [syncFilePath, setSyncFilePath] = useState<string | null>(null)
  const [compareSelectorEp, setCompareSelectorEp] = useState<EpisodeInfo | null>(null)

  // Video sync modal (ffsubsync / alass)
  const [videoSyncEp, setVideoSyncEp] = useState<{ ep: EpisodeInfo; subtitlePath: string } | null>(null)

  // Health check state
  const [healthCheckPath, setHealthCheckPath] = useState<string | null>(null)
  const [healthScores, setHealthScores] = useState<Record<string, number | null>>({})

  // Interactive search modal state
  const [interactiveEp, setInteractiveEp] = useState<{ id: number; title: string } | null>(null)

  const episodeSearch = useEpisodeSearch()
  const _episodeHistory = useEpisodeHistory(expandedEp?.mode === 'history' ? expandedEp.id : 0)
  const processItem = useProcessWantedItem()
  const startSeriesSearch = useStartWantedBatch()
  const [seriesSearchStarted, setSeriesSearchStarted] = useState(false)

  // Fansub override indicator
  const { data: fansubPrefs } = useSeriesFansubPrefs(seriesId ?? -1)
  const hasFansubOverride = seriesId !== null && (
    (fansubPrefs?.preferred_groups.length ?? 0) > 0 ||
    (fansubPrefs?.excluded_groups.length ?? 0) > 0
  )

  // AniDB absolute order
  const updateSeriesSettingsMutation = useUpdateSeriesSettings()

  // Re-scan series
  const [isRescanning, setIsRescanning] = useState(false)
  const rescanSeriesMutation = useRescanSeries()
  const refreshAnidbMappingMutation = useRefreshAnidbMapping()

  const handleToggleAbsoluteOrder = useCallback((enabled: boolean) => {
    if (!seriesId) return
    updateSeriesSettingsMutation.mutate(
      { seriesId, settings: { absolute_order: enabled } },
      {
        onSuccess: () => toast(enabled ? 'Absolute order enabled' : 'Absolute order disabled'),
        onError: () => toast('Failed to update series settings', 'error'),
      }
    )
  }, [seriesId, updateSeriesSettingsMutation])

  const handleRefreshAnidbMapping = useCallback(() => {
    refreshAnidbMappingMutation.mutate(undefined, {
      onSuccess: () => toast('AniDB mapping refresh started'),
      onError: () => toast('Failed to refresh AniDB mapping', 'error'),
    })
  }, [refreshAnidbMappingMutation])

  const handleSearchAllEpisodes = useCallback(() => {
    if (!seriesId) return
    startSeriesSearch.mutate({ seriesId }, {
      onSuccess: (data) => {
        setSeriesSearchStarted(true)
        toast(`Suche gestartet für ${data.total_items} Episoden`, 'success')
      },
      onError: () => toast('Suche konnte nicht gestartet werden', 'error'),
    })
  }, [seriesId, startSeriesSearch])

  const handleSearch = useCallback((ep: EpisodeInfo) => {
    if (expandedEp?.id === ep.id && expandedEp?.mode === 'search') {
      setExpandedEp(null)
      return
    }
    setExpandedEp({ id: ep.id, mode: 'search' })
    episodeSearch.mutate(ep.id, {
      onSuccess: (data) => {
        setSearchResults((prev) => ({ ...prev, [ep.id]: data }))
      },
      onError: () => {
        toast('Search failed', 'error')
      },
    })
  }, [expandedEp, episodeSearch])

  const handleHistory = useCallback((ep: EpisodeInfo) => {
    if (expandedEp?.id === ep.id && expandedEp?.mode === 'history') {
      setExpandedEp(null)
      return
    }
    setExpandedEp({ id: ep.id, mode: 'history' })
    // Fetch history via mutation-style (since the hook is lazy)
    import('@/api/client').then(({ episodeHistory: fetchHistory }) => {
      fetchHistory(ep.id).then((data) => {
        setHistoryEntries((prev) => ({ ...prev, [ep.id]: data.entries }))
      }).catch(() => {
        setHistoryEntries((prev) => ({ ...prev, [ep.id]: [] }))
        toast('Failed to load history', 'error')
      })
    })
  }, [expandedEp])

  const handleProcess = useCallback((wantedId: number) => {
    processItem.mutate(wantedId, {
      onSuccess: () => {
        toast('Download started')
      },
      onError: () => {
        toast('Download failed', 'error')
      },
    })
  }, [processItem])

  const handleClose = useCallback(() => {
    setExpandedEp(null)
  }, [])

  const handleTracks = useCallback((ep: EpisodeInfo) => {
    if (expandedEp?.id === ep.id && expandedEp?.mode === 'tracks') {
      setExpandedEp(null)
      return
    }
    setExpandedEp({ id: ep.id, mode: 'tracks' })
  }, [expandedEp])

  const handleCompare = useCallback((ep: EpisodeInfo) => {
    setCompareSelectorEp(ep)
  }, [])

  const handleSync = useCallback((filePath: string) => {
    setSyncFilePath(filePath)
  }, [])

  const handleAutoSync = useCallback((subtitlePath: string, videoPath: string) => {
    toast('Auto-syncing…', 'info')
    void autoSyncFile(subtitlePath, videoPath).then(() => {
      toast('Auto-sync gestartet')
    }).catch((err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Auto-sync fehlgeschlagen'
      toast(msg, 'error')
    })
  }, [])

  const handleVideoSync = useCallback((ep: EpisodeInfo, subtitlePath: string) => {
    setVideoSyncEp({ ep, subtitlePath })
  }, [])

  const handleHealthCheck = useCallback((filePath: string) => {
    setHealthCheckPath(filePath)
  }, [])

  const extractTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleExtract = useCallback(() => {
    if (seriesId == null || extractProgress !== null) return
    setExtractProgress({ current: 0, total: 0, filename: '' })
    // Safety fallback: clear stuck state after 10 minutes
    if (extractTimeoutRef.current) clearTimeout(extractTimeoutRef.current)
    extractTimeoutRef.current = setTimeout(() => {
      setExtractProgress(null)
      void queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })
      void queryClient.invalidateQueries({ queryKey: ['series', seriesId] })
    }, 10 * 60 * 1000)
    batchExtractAllTracks(seriesId).catch((err: unknown) => {
      setExtractProgress(null)
      if (extractTimeoutRef.current) clearTimeout(extractTimeoutRef.current)
      const msg = err instanceof Error ? err.message : 'Extraktion fehlgeschlagen'
      toast(msg, 'error')
    })
  }, [seriesId, extractProgress, queryClient])

  const handlePreview = useCallback((ep: EpisodeInfo) => {
    const epSidecars = sidecarMap[String(ep.id)] ?? []
    const tracks: PlayerSubtitleTrack[] = epSidecars
      .filter((s) => s.format === 'ass' || s.format === 'srt' || s.format === 'vtt')
      .map((s) => ({
        path: s.path,
        language: s.language,
        format: s.format as 'ass' | 'srt' | 'vtt',
        label: `${s.language.toUpperCase()} — ${s.format.toUpperCase()}`,
      }))
    setPlayerState({ videoPath: ep.file_path, tracks })
  }, [sidecarMap])

  const handleDeleteSidecar = useCallback((path: string): Promise<void> => {
    setDeleteAlsoBlacklist(false)
    setDeleteConfirm(path)
    return Promise.resolve()
  }, [])

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteConfirm) return
    const path = deleteConfirm
    setDeleteConfirm(null)
    try {
      await deleteSubtitles([path], deleteAlsoBlacklist)
      if (deleteAlsoBlacklist) {
        toast('Untertitel gelöscht und gesperrt', 'success')
        queryClient.invalidateQueries({ queryKey: ['blacklist'] })
      } else {
        toast('Sidecar gelöscht')
      }
      await queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })
    } catch {
      toast('Löschen fehlgeschlagen', 'error')
    }
  }, [deleteConfirm, deleteAlsoBlacklist, queryClient, seriesId])

  // Group episodes by season
  const seasonGroups = useMemo(() => {
    if (!series?.episodes) return []
    const groups = new Map<number, EpisodeInfo[]>()
    for (const ep of series.episodes) {
      if (!groups.has(ep.season)) {
        groups.set(ep.season, [])
      }
      groups.get(ep.season)!.push(ep)
    }
    return Array.from(groups.entries())
      .sort((a, b) => a[0] - b[0]) // Ascending order for tabs
  }, [series?.episodes])

  const [activeSeason, setActiveSeason] = useState<number | null>(null)
  const [showSeriesSettings, setShowSeriesSettings] = useState(false)

  // Default to the first season (lowest number)
  const defaultSeason = seasonGroups[0]?.[0] ?? null
  const currentSeason = activeSeason ?? defaultSeason
  const currentEpisodes = seasonGroups.find(([s]) => s === currentSeason)?.[1] ?? []

  // Count missing subs — align with Library's definition:
  // only episodes where existing_sub is '' or null/undefined (no subtitle at all).
  // 'srt', 'embedded_srt', 'embedded_ass', 'ass' etc. are NOT missing — they are
  // upgrade candidates or already satisfied, matching get_series_missing_counts() logic.
  const missingCount = useMemo(() => {
    if (!series?.episodes) return 0
    let count = 0
    for (const ep of series.episodes) {
      if (!ep.has_file) continue
      for (const lang of series.target_languages) {
        const sub = ep.subtitles[lang]
        if (sub == null || sub === '') {
          count++
        }
      }
    }
    return count
  }, [series])

  const withSubsCount = useMemo(() => {
    if (!series?.episodes) return 0
    return series.episodes.filter(
      (ep) => ep.has_file && series.target_languages.some(
        (lang) => { const f = ep.subtitles[lang]; return f != null && f !== '' }
      )
    ).length
  }, [series])

  const LOW_SCORE_THRESHOLD = 60
  const lowScoreCount = useMemo(() => {
    if (!series?.episodes) return 0
    return series.episodes.filter((ep) => {
      if (!ep.has_file) return false
      return series.target_languages.some((lang) => {
        const score = ep.subtitle_scores?.[lang] ?? null
        const fmt = ep.subtitles[lang]
        return fmt != null && fmt !== '' && score !== null && score < LOW_SCORE_THRESHOLD
      })
    }).length
  }, [series])

  const handleRescan = useCallback(() => {
    if (!seriesId) return
    setIsRescanning(true)
    rescanSeriesMutation.mutate(seriesId, {
      onSuccess: () => {
        toast('Re-scan started', 'success')
        setIsRescanning(false)
      },
      onError: () => {
        toast('Re-scan failed', 'error')
        setIsRescanning(false)
      },
    })
  }, [seriesId, rescanSeriesMutation])

  const handleNfoExport = useCallback(async () => {
    if (!seriesId) return
    try {
      const blob = await exportSeriesNfo(seriesId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `series-${seriesId}-nfo.zip`
      a.click()
      URL.revokeObjectURL(url)
      toast('NFO exported', 'success')
    } catch {
      toast('NFO export failed', 'error')
    }
  }, [seriesId])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  if (error || !series) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/library')}
          className="flex items-center gap-2 text-sm transition-colors"
          style={{ color: 'var(--text-secondary)' }}
        >
          <ArrowLeft size={14} />
          {t('series_detail.back_to_library')}
        </button>
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <p style={{ color: 'var(--error)' }}>{t('series_detail.failed_to_load')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4 animate-in">
      {/* Breadcrumb navigation */}
      <div className="flex items-center justify-between">
        <Breadcrumb items={[{ label: 'Library', href: '/library' }, { label: series.title }]} />
        {/* Hidden back button for tests */}
        <button
          data-testid="series-back-btn"
          onClick={() => navigate('/library')}
          className="sr-only"
          aria-hidden="true"
        >
          <ArrowLeft size={14} />
          Back to Library
        </button>
      </div>

      {/* Hero Header */}
      <SeriesHero
        series={series}
        missingCount={missingCount}
        withSubsCount={withSubsCount}
        lowScoreCount={lowScoreCount}
        isMissingSearchPending={startSeriesSearch.isPending}
        missingSearchStarted={seriesSearchStarted}
        onSearchAllMissing={handleSearchAllEpisodes}
        onRescan={handleRescan}
        isRescanning={isRescanning}
        onNfoExport={handleNfoExport}
        onSeriesSettings={() => setShowSeriesSettings((v) => !v)}
      />

      {/* Series Settings Panel (collapsible) */}
      {showSeriesSettings && seriesId !== null && (
        <SeriesSettingsPanel
          series={series}
          seriesId={seriesId}
          showGlossary={showGlossary}
          hasFansubOverride={hasFansubOverride}
          isExtracting={extractProgress !== null}
          extractProgress={extractProgress}
          onToggleGlossary={() => setShowGlossary((v) => !v)}
          onToggleAbsoluteOrder={handleToggleAbsoluteOrder}
          onRefreshAnidb={handleRefreshAnidbMapping}
          onExtract={handleExtract}
          onCleanup={() => setShowCleanupModal(true)}
          onFansub={() => setFansubOpen(true)}
          exportUrl={getSeriesSubtitleExportUrl(series.id)}
          updatePending={updateSeriesSettingsMutation.isPending}
          refreshPending={refreshAnidbMappingMutation.isPending}
        />
      )}

      {/* Glossary Panel */}
      {showGlossary && (
        <div
          className="rounded-lg overflow-hidden"
          style={{ border: '1px solid var(--border)' }}
        >
          {seriesId !== null && <GlossaryPanel seriesId={seriesId} />}
        </div>
      )}

      {/* Extraction Progress Banner */}
      {extractProgress && (
        <div
          className="px-4 py-3 rounded-lg"
          style={{ backgroundColor: 'var(--accent-bg)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="flex items-center gap-2 mb-2">
            <Loader2 size={13} className="animate-spin flex-shrink-0" style={{ color: 'var(--accent)' }} />
            <span className="text-xs font-semibold" style={{ color: 'var(--accent)' }}>
              {extractProgress.total === 0
                ? 'Extraktion wird gestartet…'
                : `Extrahiere Tracks — ${extractProgress.current} / ${extractProgress.total} Episoden`}
            </span>
            {extractProgress.filename && (
              <span
                className="text-xs truncate"
                style={{ color: 'var(--text-muted)', maxWidth: '340px' }}
                title={extractProgress.filename}
              >
                · {extractProgress.filename}
              </span>
            )}
          </div>
          <ProgressBar value={extractProgress.total === 0 ? 0 : extractProgress.current} max={extractProgress.total === 0 ? 100 : extractProgress.total} showLabel={false} />
        </div>
      )}

      {/* Season tabs */}
      {seasonGroups.length > 0 && (
        <SeasonTabs
          seasons={seasonGroups.map(([s]) => s)}
          activeSeason={currentSeason ?? 0}
          onSeasonChange={setActiveSeason}
        />
      )}

      {/* Season summary bar + search button */}
      {currentSeason !== null && (
        <div className="flex items-center gap-2">
          <div className="flex-1">
            <SeasonSummaryBar
              season={currentSeason}
              episodes={currentEpisodes}
              targetLanguages={series.target_languages}
            />
          </div>
          <button
            className="flex-shrink-0 text-xs px-3 py-1.5 rounded"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              cursor: startSeriesSearch.isPending ? 'not-allowed' : 'pointer',
              opacity: startSeriesSearch.isPending ? 0.5 : 1,
            }}
            disabled={startSeriesSearch.isPending}
            onClick={() => startSeriesSearch.mutate(
              { seriesId: seriesId ?? undefined },
              {
                onSuccess: () => toast('Season search started'),
                onError: () => toast('Search failed', 'error'),
              }
            )}
            data-testid={`search-season-${currentSeason}`}
          >
            Search Season {currentSeason}
          </button>
        </div>
      )}

      {/* Column header row */}
      <EpisodeGridHeader />

      {/* Episode list — individual cards matching mockup */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {currentSeason !== null && currentEpisodes.length > 0 ? (
          <SeasonGroup
            season={currentSeason}
            episodes={currentEpisodes}
            targetLanguages={series.target_languages}
            seriesId={seriesId}
            isExtracting={extractProgress !== null}
            onExtract={handleExtract}
            expandedEp={expandedEp}
            onSearch={handleSearch}
            onInteractiveSearch={(ep) => setInteractiveEp({ id: ep.id, title: `${series.title} ${ep.title ? `– ${ep.title}` : ''}`.trim() })}
            onHistory={handleHistory}
            onTracks={handleTracks}
            onClose={handleClose}
            searchResults={expandedEp ? searchResults[expandedEp.id] ?? null : null}
            searchLoading={episodeSearch.isPending}
            historyEntries={expandedEp ? historyEntries[expandedEp.id] ?? [] : []}
            historyLoading={expandedEp?.mode === 'history' && !(expandedEp.id in historyEntries)}
            onProcess={handleProcess}
            onPreviewSub={(path) => { setEditorFilePath(path); setEditorMode('preview') }}
            onEditSub={(path) => { setEditorFilePath(path); setEditorMode('edit') }}
            onCompare={handleCompare}
            onSync={handleSync}
            onAutoSync={handleAutoSync}
            onVideoSync={handleVideoSync}
            onHealthCheck={handleHealthCheck}
            healthScores={healthScores}
            onOpenEditor={(path) => { setEditorFilePath(path); setEditorMode('edit') }}
            sidecarMap={sidecarMap}
            onDeleteSidecar={handleDeleteSidecar}
            onOpenCleanupModal={() => setShowCleanupModal(true)}
            onPreview={handlePreview}
            streamingEnabled={streamingEnabled ?? false}
            onRefreshSidecars={() => queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })}
            t={t}
            episodeWantedMap={episodeWantedMap}
            onSkipEpisode={(episodeId) => {
              const wantedId = episodeWantedMap.get(episodeId)
              if (wantedId != null) updateWantedStatus.mutate({ itemId: wantedId, status: 'ignored' })
            }}
            onAcceptEpisode={(episodeId) => {
              const wantedId = episodeWantedMap.get(episodeId)
              if (wantedId != null) updateWantedStatus.mutate({ itemId: wantedId, status: 'ignored' })
            }}
          />
        ) : seasonGroups.length === 0 ? (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
            {t('series_detail.no_episodes')}
          </div>
        ) : null}
      </div>

      {/* Sidecar Cleanup Modal */}
      {showCleanupModal && seriesId != null && (
        <SubtitleCleanupModal
          seriesId={seriesId}
          targetLanguages={series?.target_languages ?? []}
          onClose={() => setShowCleanupModal(false)}
        />
      )}

      {/* Delete Sidecar Confirmation Dialog */}
      {deleteConfirm && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          onClick={(e) => { if (e.target === e.currentTarget) setDeleteConfirm(null) }}
        >
          <div
            className="w-full max-w-sm mx-4 rounded-xl p-5 space-y-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                <Trash2 size={16} style={{ color: 'var(--error)' }} />
                <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                  Untertitel löschen
                </h3>
              </div>
              <button
                onClick={() => setDeleteConfirm(null)}
                className="p-1 rounded"
                style={{ color: 'var(--text-muted)' }}
              >
                <X size={14} />
              </button>
            </div>

            <div
              className="text-xs px-2 py-1.5 rounded truncate"
              style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
              title={deleteConfirm}
            >
              {deleteConfirm.split('/').pop() ?? deleteConfirm}
            </div>

            <label className="flex items-center gap-2 cursor-pointer text-sm select-none" style={{ color: 'var(--text-secondary)' }}>
              <input
                type="checkbox"
                checked={deleteAlsoBlacklist}
                onChange={(e) => setDeleteAlsoBlacklist(e.target.checked)}
                className="rounded"
              />
              Auch zur Sperrliste hinzufügen
            </label>

            <div className="flex gap-2 justify-end pt-1">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-3 py-1.5 rounded-md text-sm transition-colors"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
              >
                Abbrechen
              </button>
              <button
                onClick={handleDeleteConfirm}
                className="px-3 py-1.5 rounded-md text-sm font-medium transition-colors"
                style={{ backgroundColor: 'var(--error)', color: 'white' }}
              >
                Löschen
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Subtitle Editor Modal */}
      {editorFilePath && (
        <SubtitleEditorModal
          filePath={editorFilePath}
          initialMode={editorMode}
          onClose={() => setEditorFilePath(null)}
          onSeekRequest={playerState ? (seconds) => seekFnRef.current?.(seconds) : undefined}
        />
      )}

      {/* Comparison Selector Modal */}
      {compareSelectorEp && series && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setCompareSelectorEp(null)
          }}
        >
          <div className="w-full max-w-md mx-4">
            <ComparisonSelector
              availableFiles={
                Object.entries(compareSelectorEp.subtitles)
                  .filter(([, f]) => f === 'ass' || f === 'srt')
                  .map(([lang, fmt]) => ({
                    path: deriveSubtitlePath(compareSelectorEp.file_path, lang, fmt),
                    label: `${lang.toUpperCase()} (${fmt.toUpperCase()})`,
                  }))
              }
              onCompare={(paths) => {
                setComparisonPaths(paths)
                setCompareSelectorEp(null)
              }}
              onClose={() => setCompareSelectorEp(null)}
            />
          </div>
        </div>,
        document.body
      )}

      {/* Comparison View Modal */}
      {comparisonPaths && createPortal(
        <div
          className="fixed inset-0 z-50 flex flex-col"
          style={{ backgroundColor: 'var(--bg-primary)' }}
        >
          <Suspense
            fallback={
              <div className="flex flex-1 items-center justify-center" style={{ color: 'var(--text-muted)' }}>
                <Loader2 size={24} className="animate-spin" />
              </div>
            }
          >
            <SubtitleComparison
              filePaths={comparisonPaths}
              onClose={() => setComparisonPaths(null)}
            />
          </Suspense>
        </div>,
        document.body
      )}

      {/* Sync Controls Modal */}
      {syncFilePath && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setSyncFilePath(null)
          }}
        >
          <div className="w-full max-w-lg mx-4">
            <Suspense
              fallback={
                <div
                  className="rounded-lg p-8 flex items-center justify-center"
                  style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
                >
                  <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
                </div>
              }
            >
              <SyncControls
                filePath={syncFilePath}
                onSynced={() => setSyncFilePath(null)}
                onClose={() => setSyncFilePath(null)}
              />
            </Suspense>
          </div>
        </div>,
        document.body
      )}

      {/* Video Sync Modal (ffsubsync / alass) */}
      {videoSyncEp && (
        <Suspense fallback={null}>
          <SyncModal
            episodeId={videoSyncEp.ep.id}
            subtitlePath={videoSyncEp.subtitlePath}
            videoPath={videoSyncEp.ep.file_path}
            onClose={() => setVideoSyncEp(null)}
            onComplete={() => {
              toast('Video-Sync abgeschlossen')
              setVideoSyncEp(null)
            }}
          />
        </Suspense>
      )}

      {/* Interactive Search Modal */}
      <InteractiveSearchModal
        open={!!interactiveEp}
        episodeId={interactiveEp?.id}
        itemTitle={interactiveEp?.title ?? ''}
        onClose={() => setInteractiveEp(null)}
        onDownloaded={() => setInteractiveEp(null)}
      />

      {/* Web Player Modal */}
      {playerState && (
        <PlayerModal
          videoPath={playerState.videoPath}
          subtitleTracks={playerState.tracks}
          onClose={() => setPlayerState(null)}
          onSeekReady={(fn) => { seekFnRef.current = fn }}
        />
      )}

      {/* Health Check Panel Modal */}
      {healthCheckPath && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setHealthCheckPath(null)
          }}
        >
          <div className="w-full max-w-lg mx-4">
            <Suspense
              fallback={
                <div
                  className="rounded-lg p-8 flex items-center justify-center"
                  style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
                >
                  <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
                </div>
              }
            >
              <HealthCheckPanel
                filePath={healthCheckPath}
                onClose={() => setHealthCheckPath(null)}
                onFixed={() => {
                  // Update health scores cache when a fix is applied
                  import('@/api/client').then(({ runHealthCheck }) => {
                    runHealthCheck(healthCheckPath).then((result) => {
                      setHealthScores((prev) => ({ ...prev, [healthCheckPath]: result.score }))
                    }).catch(() => { /* ignore */ })
                  })
                }}
              />
            </Suspense>
          </div>
        </div>,
        document.body
      )}

      {seriesId !== null && (
        <FansubOverrideModal
          seriesId={seriesId}
          open={fansubOpen}
          onClose={() => setFansubOpen(false)}
        />
      )}
    </div>
  )
}
