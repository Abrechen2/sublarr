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
import { autoSyncFile, batchExtractAllTracks, listSeriesSubtitles, deleteSubtitles, exportSeriesSubtitles, exportSeriesNfo } from '@/api/client'
import { scanSeriesHealth } from '@/api/subtitleHealth'
import { useWebSocket } from '@/hooks/useWebSocket'
import { ProgressBar } from '@/components/shared/ProgressBar'
import { InteractiveSearchModal } from '@/components/wanted/InteractiveSearchModal'
import { CombineDialog } from '@/components/episodes/CombineDialog'
import { ComparisonSelector } from '@/components/comparison/ComparisonSelector'
import { SubtitleCleanupModal } from '@/components/shared/SubtitleCleanupModal'
import { ExtractConfirmModal } from '@/components/series/ExtractConfirmModal'
import type { EpisodeInfo, WantedSearchResponse, EpisodeHistoryEntry, SidecarSubtitle } from '@/lib/types'
import { FansubOverrideModal } from '@/components/series/FansubOverrideModal'
import { deriveSubtitlePath } from '@/components/series/seriesUtils'

import { GlossaryPanel } from '@/components/series/GlossaryPanel'
import { SeasonGroup } from '@/components/series/SeasonGroup'
import { EpisodeGridHeader } from '@/components/series/EpisodeGrid'
import { SeriesHero } from '@/components/series/SeriesHero'
import { SeriesSettingsPanel } from '@/components/series/SeriesSettingsPanel'
import { SeasonTabs } from '@/components/series/SeasonTabs'
import SeriesOverrideSettings from '@/components/library/SeriesOverrideSettings'
import { updateSeriesSettings as patchSeriesSettings } from '@/api/seriesSettings'
import { useMutation } from '@tanstack/react-query'

const SubtitleComparison = lazy(() => import('@/components/comparison/SubtitleComparison').then(m => ({ default: m.SubtitleComparison })))
const SyncControls = lazy(() => import('@/components/sync/SyncControls').then(m => ({ default: m.SyncControls })))
const SyncModal = lazy(() => import('@/components/sync/SyncModal').then(m => ({ default: m.SyncModal })))
const SyncOutputCompareModal = lazy(() => import('@/components/sync/SyncOutputCompareModal').then(m => ({ default: m.SyncOutputCompareModal })))
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

  // Subtitle editor modal state — tracks both the subtitle and the source
  // video so the modal can show the Waveform tab (Plan B8).
  const [editorFilePath, setEditorFilePath] = useState<string | null>(null)
  const [editorVideoPath, setEditorVideoPath] = useState<string | null>(null)
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
  const [showExtractConfirm, setShowExtractConfirm] = useState(false)
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
        ? `${t('series_detail.tracks_extracted', { count: d.succeeded })}${d.failed > 0 ? t('series_detail.tracks_failed_suffix', { count: d.failed }) : ''}`
        : d.failed > 0
          ? t('series_detail.extraction_failed_count', { count: d.failed })
          : t('series_detail.extraction_done_all_present')
      toast(msg, d.failed > 0 ? 'error' : 'success')
    },
  })

  // Comparison and sync state
  const [comparisonPaths, setComparisonPaths] = useState<string[] | null>(null)
  const [syncFilePath, setSyncFilePath] = useState<string | null>(null)
  const [compareSelectorEp, setCompareSelectorEp] = useState<EpisodeInfo | null>(null)
  const [combineEp, setCombineEp] = useState<EpisodeInfo | null>(null)

  // Video sync modal (ffsubsync / alass)
  const [videoSyncEp, setVideoSyncEp] = useState<{ ep: EpisodeInfo; subtitlePath: string } | null>(null)
  const [syncCompareEp, setSyncCompareEp] = useState<{ ep: EpisodeInfo; subtitlePath: string } | null>(null)

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

  // Scheduler override (priority tier + min attempts/day) — PATCH /series/<id>/settings
  const overrideMutation = useMutation({
    mutationFn: (payload: { priority_override: string | null; min_attempts_per_day: number }) => {
      if (seriesId == null) {
        return Promise.reject(new Error('No series ID'))
      }
      return patchSeriesSettings(seriesId, payload)
    },
    onSuccess: () => toast(t('series_detail.override_saved'), 'success'),
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : t('series_detail.save_failed')
      toast(msg, 'error')
    },
  })

  // Re-scan series
  const [isRescanning, setIsRescanning] = useState(false)
  const rescanSeriesMutation = useRescanSeries()
  const refreshAnidbMappingMutation = useRefreshAnidbMapping()

  const handleToggleAbsoluteOrder = useCallback((enabled: boolean) => {
    if (!seriesId) return
    updateSeriesSettingsMutation.mutate(
      { seriesId, settings: { absolute_order: enabled } },
      {
        onSuccess: () => toast(enabled ? t('series_detail.absolute_order_enabled') : t('series_detail.absolute_order_disabled')),
        onError: () => toast(t('series_detail.update_settings_failed'), 'error'),
      }
    )
  }, [seriesId, updateSeriesSettingsMutation])

  const handleSetCleanupForeignTracks = useCallback(
    (value: boolean | null) => {
      if (seriesId == null) return
      patchSeriesSettings(seriesId, { cleanup_foreign_tracks: value })
        .then(() => {
          void queryClient.invalidateQueries({ queryKey: ['series', seriesId] })
          const label =
            value === true ? t('series_detail.cleanup_always_toast') : value === false ? t('series_detail.cleanup_never_toast') : t('series_detail.cleanup_inherit_toast')
          toast(label, 'success')
        })
        .catch((err: unknown) => {
          const msg = err instanceof Error ? err.message : t('series_detail.save_failed')
          toast(msg, 'error')
        })
    },
    [seriesId, queryClient]
  )

  const handleRefreshAnidbMapping = useCallback(() => {
    refreshAnidbMappingMutation.mutate(undefined, {
      onSuccess: () => toast(t('series_detail.anidb_refresh_started')),
      onError: () => toast(t('series_detail.anidb_refresh_failed'), 'error'),
    })
  }, [refreshAnidbMappingMutation])

  const handleSearchAllEpisodes = useCallback(() => {
    if (!seriesId) return
    startSeriesSearch.mutate({ seriesId }, {
      onSuccess: (data) => {
        if (data.total_items === 0) {
          toast(t('series_detail.no_pending_wanted'), 'info')
          return
        }
        setSeriesSearchStarted(true)
        toast(`${t('series_detail.searching')} (${data.total_items})`, 'success')
      },
      onError: () => toast(t('series_detail.no_search_results'), 'error'),
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
        toast(t('series_detail.search_failed'), 'error')
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
        toast(t('series_detail.load_history_failed'), 'error')
      })
    })
  }, [expandedEp])

  const handleProcess = useCallback((wantedId: number) => {
    processItem.mutate(wantedId, {
      onSuccess: () => {
        toast(t('series_detail.download_started'))
      },
      onError: () => {
        toast(t('series_detail.download_failed'), 'error')
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

  const handleCombine = useCallback((ep: EpisodeInfo) => {
    setCombineEp(ep)
  }, [])

  const handleSync = useCallback((filePath: string) => {
    setSyncFilePath(filePath)
  }, [])

  const handleAutoSync = useCallback((subtitlePath: string, videoPath: string) => {
    toast(t('series_detail.auto_syncing'), 'info')
    void autoSyncFile(subtitlePath, videoPath).then(() => {
      toast(t('series_detail.auto_sync_started'))
    }).catch((err: unknown) => {
      const msg = err instanceof Error ? err.message : t('series_detail.auto_sync_failed')
      toast(msg, 'error')
    })
  }, [])

  const handleVideoSync = useCallback((ep: EpisodeInfo, subtitlePath: string) => {
    setVideoSyncEp({ ep, subtitlePath })
  }, [])

  const handleSyncCompare = useCallback((ep: EpisodeInfo, subtitlePath: string) => {
    setSyncCompareEp({ ep, subtitlePath })
  }, [])

  const handleHealthCheck = useCallback((filePath: string) => {
    setHealthCheckPath(filePath)
  }, [])

  const extractTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleExtractConfirmed = useCallback(() => {
    setShowExtractConfirm(false)
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
      const msg = err instanceof Error ? err.message : t('series_detail.extraction_failed')
      toast(msg, 'error')
    })
  }, [seriesId, extractProgress, queryClient])

  const handleExtract = useCallback(() => {
    if (seriesId == null || extractProgress !== null) return
    setShowExtractConfirm(true)
  }, [seriesId, extractProgress])

  const handleExport = useCallback(() => {
    if (seriesId == null) return
    exportSeriesSubtitles(seriesId).catch((err: unknown) => {
      const msg = err instanceof Error ? err.message : t('series_detail.export_failed')
      toast(msg, 'error')
    })
  }, [seriesId])

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
        toast(t('series_detail.subtitle_deleted_blacklisted'), 'success')
        queryClient.invalidateQueries({ queryKey: ['blacklist'] })
      } else {
        toast(t('series_detail.sidecar_deleted'))
      }
      await queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })
    } catch {
      toast(t('series_detail.delete_failed'), 'error')
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

  // Default to the first REAL season — season 0 holds specials, which are
  // often fileless placeholders and made complete series look broken when
  // shown first. Fall back to season 0 only if it is the only season.
  const defaultSeason =
    seasonGroups.find(([s]) => s > 0)?.[0] ?? seasonGroups[0]?.[0] ?? null
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
        toast(t('series_detail.rescan_started'), 'success')
        setIsRescanning(false)
      },
      onError: () => {
        toast(t('series_detail.rescan_failed'), 'error')
        setIsRescanning(false)
      },
    })
  }, [seriesId, rescanSeriesMutation])

  const handleScanHealth = useCallback(async () => {
    if (!seriesId) return
    try {
      await scanSeriesHealth(seriesId)
      // Background job; findings surface per-episode and in Settings → System → Subtitle Health.
      toast(t('subtitle_health.scan_series_started'), 'success')
    } catch {
      toast(t('series_detail.rescan_failed'), 'error')
    }
  }, [seriesId, t])

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
      toast(t('series_detail.nfo_exported'), 'success')
    } catch {
      toast(t('series_detail.nfo_export_failed'), 'error')
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
        <Breadcrumb items={[{ label: t('series_detail.breadcrumb_library'), href: '/library' }, { label: series.title }]} />
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
          onSetCleanupForeignTracks={handleSetCleanupForeignTracks}
          onRefreshAnidb={handleRefreshAnidbMapping}
          onExtract={handleExtract}
          onCleanup={() => setShowCleanupModal(true)}
          onFansub={() => setFansubOpen(true)}
          onExport={handleExport}
          onScanHealth={handleScanHealth}
          updatePending={updateSeriesSettingsMutation.isPending}
          refreshPending={refreshAnidbMappingMutation.isPending}
        />
      )}

      {/* Scheduler Override (Phase 4a) — appended as a separate card so the
          protected SeriesSettingsPanel stays untouched. */}
      {showSeriesSettings && seriesId !== null && (
        <div
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            padding: '16px',
            marginBottom: '16px',
          }}
        >
          <SeriesOverrideSettings
            seriesId={seriesId}
            initial={{
              priority_override: null,
              min_attempts_per_day: 0,
              subtitle_format_requirement: null,
            }}
            onSave={(payload) => overrideMutation.mutate(payload)}
          />
        </div>
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
                ? t('series_detail.extraction_starting')
                : t('series_detail.extracting_tracks_progress', { current: extractProgress.current, total: extractProgress.total })}
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
                onSuccess: () => toast(t('series_detail.searching')),
                onError: () => toast(t('series_detail.no_search_results'), 'error'),
              }
            )}
            data-testid={`search-season-${currentSeason}`}
          >
            {t('series_detail.search_season', { number: currentSeason })}
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
            onPreviewSub={(path, videoPath) => {
              setEditorFilePath(path)
              setEditorVideoPath(videoPath)
              setEditorMode('preview')
            }}
            onEditSub={(path, videoPath) => {
              setEditorFilePath(path)
              setEditorVideoPath(videoPath)
              setEditorMode('edit')
            }}
            onCompare={handleCompare}
            onCombine={handleCombine}
            onSync={handleSync}
            onAutoSync={handleAutoSync}
            onVideoSync={handleVideoSync}
            onSyncCompare={handleSyncCompare}
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

      {/* Extract Confirm Modal */}
      <ExtractConfirmModal
        open={showExtractConfirm}
        onConfirm={handleExtractConfirmed}
        onCancel={() => setShowExtractConfirm(false)}
      />

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
                  {t('series_detail.delete_subtitle_title')}
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
              {t('series_detail.also_blacklist')}
            </label>

            <div className="flex gap-2 justify-end pt-1">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-3 py-1.5 rounded-md text-sm transition-colors"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
              >
                {t('series_detail.cancel')}
              </button>
              <button
                onClick={handleDeleteConfirm}
                className="px-3 py-1.5 rounded-md text-sm font-medium transition-colors"
                style={{ backgroundColor: 'var(--error)', color: 'white' }}
              >
                {t('series_detail.delete')}
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
          videoPath={editorVideoPath ?? undefined}
          initialMode={editorMode}
          onClose={() => {
            setEditorFilePath(null)
            setEditorVideoPath(null)
          }}
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
              toast(t('series_detail.video_sync_done'))
              setVideoSyncEp(null)
            }}
          />
        </Suspense>
      )}

      {/* Sync Compare Modal (non-destructive preview) */}
      {syncCompareEp && (
        <Suspense fallback={null}>
          <SyncOutputCompareModal
            subtitlePath={syncCompareEp.subtitlePath}
            videoPath={syncCompareEp.ep.file_path}
            onClose={() => setSyncCompareEp(null)}
            onApplied={() => {
              setSyncCompareEp(null)
              void queryClient.invalidateQueries({ queryKey: ['series-subtitles', seriesId] })
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

      {/* Combine Subtitles Dialog */}
      {combineEp && seriesId != null && (
        <CombineDialog
          open={!!combineEp}
          episodeId={combineEp.id}
          episodeTitle={`${series.title} — S${String(combineEp.season).padStart(2, '0')}E${String(combineEp.episode).padStart(2, '0')}${combineEp.title ? ` · ${combineEp.title}` : ''}`}
          availableLanguages={Object.entries(combineEp.subtitles)
            .filter(([, fmt]) => fmt)
            .map(([lang]) => lang)}
          targetLanguages={series.target_languages}
          seriesId={seriesId}
          onClose={() => setCombineEp(null)}
        />
      )}

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
