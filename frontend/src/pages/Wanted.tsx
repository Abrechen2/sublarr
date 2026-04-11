import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useDebounce } from '@/hooks/useDebounce'
import { useTranslation } from 'react-i18next'
import {
  useInfiniteWantedItems, useWantedSummary, useRefreshWanted, useUpdateWantedStatus,
  useProcessWantedItem, useStartWantedBatch, useWantedBatchStatus,
  useWantedBatchExtractStatus, useWantedBatchProbeStatus, useStartBatchProbe,
  useRetranslateSingle, useAddToBlacklist, useExtractEmbeddedSub,
  useCleanupSidecars, useTranslationEnabled,
} from '@/hooks/useApi'
import { useBatchTranslate } from '@/hooks/useTranslationApi'
import { toast } from '@/components/shared/Toast'
import type { WantedSearchResponse } from '@/lib/types'
import type { WantedItem } from '@/types/wanted'
import { Loader2, CheckSquare, Square, MinusSquare, Download } from 'lucide-react'
import SubtitleEditorModal from '@/components/editor/SubtitleEditorModal'
import { PageHeader } from '@/components/layout/PageHeader'
import { InteractiveSearchModal } from '@/components/wanted/InteractiveSearchModal'
import type { FilterDef, ActiveFilter } from '@/components/filters/FilterBar'
import { BatchActionBar } from '@/components/batch/BatchActionBar'
import { useSelectionStore } from '@/stores/selectionStore'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useQueryClient, useQuery } from '@tanstack/react-query'
import { getConfig } from '@/api/settings'
import { WantedToolbar } from './wanted/WantedToolbar'
import { WantedFilterPanel } from './wanted/WantedFilterPanel'
import { WantedGroupedRow } from './wanted/WantedGroupedRow'
import type { WantedGroup } from '@/types/wanted'
// Re-exported for backward compat — existing tests import from here.
export { FailureReasonRow, formatRetryCountdown } from './wanted/WantedTableRow'

const SCOPE = 'wanted' as const

export function groupByFilePath(items: WantedItem[]): WantedGroup[] {
  const map = new Map<string, WantedGroup>()
  for (const item of items) {
    const key = item.file_path
    if (!map.has(key)) {
      map.set(key, {
        key,
        title: item.title,
        season_episode: item.season_episode,
        file_path: item.file_path,
        item_type: item.item_type,
        instance_name: item.instance_name,
        languages: [],
      })
    }
    map.get(key)!.languages.push(item)
  }
  for (const group of map.values()) {
    group.languages.sort((a, b) => a.target_language.localeCompare(b.target_language))
  }
  return Array.from(map.values())
}

export function WantedPage() {
  const { t } = useTranslation('library')

  const wantedFilters = useMemo<FilterDef[]>(() => [
    { key: 'status', label: t('wanted.status_col'), type: 'select' as const, options: [
      { value: 'wanted', label: t('wanted.wanted_status') },
      { value: 'ignored', label: t('wanted.ignored') },
      { value: 'failed', label: t('wanted.failed') },
      { value: 'found', label: t('wanted.found') },
    ]},
    { key: 'item_type', label: t('wanted.type_col', 'Type'), type: 'select' as const, options: [
      { value: 'episode', label: t('wanted.episodes') },
      { value: 'movie', label: t('wanted.movie') },
    ]},
    { key: 'subtitle_type', label: t('wanted.subtitle_type_col', 'Subtitle Type'), type: 'select' as const, options: [
      { value: 'full', label: t('wanted.subtitle_type_full') },
      { value: 'forced', label: t('wanted.subtitle_type_forced') },
    ]},
    { key: 'title', label: t('wanted.title_col'), type: 'text' as const },
  ], [t])
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [typeFilter, setTypeFilter] = useState<string | undefined>()
  const [subtitleTypeFilter, setSubtitleTypeFilter] = useState<string | undefined>()
  const [upgradeFilter, setUpgradeFilter] = useState(false)
  const [languageFilter, setLanguageFilter] = useState<string | undefined>()
  const [expandedItem, setExpandedItem] = useState<number | null>(null)
  const [searchResults, setSearchResults] = useState<Record<number, WantedSearchResponse>>({})
  const [searchingItems, setSearchingItems] = useState<Set<number>>(new Set())
  const [previewFilePath, setPreviewFilePath] = useState<string | null>(null)
  const [interactiveItem, setInteractiveItem] = useState<{ id: number; title: string } | null>(null)

  // FilterBar state
  const [activeFilters, setActiveFilters] = useState<ActiveFilter[]>([])
  const [sortBy, setSortBy] = useState('added_at')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [searchText, setSearchText] = useState('')
  const debouncedSearch = useDebounce(searchText, 300)

  // Zustand selection store
  const scopeSelections = useSelectionStore((s) => s.selections[SCOPE])
  const toggleItem = useSelectionStore((s) => s.toggleItem)
  const selectAll = useSelectionStore((s) => s.selectAll)
  const clearSelection = useSelectionStore((s) => s.clearSelection)
  const isSelected = useCallback((id: number) => (scopeSelections ?? new Set()).has(id), [scopeSelections])
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: getConfig })
  const sourceLanguage = (config?.source_language as string | undefined) ?? 'en'
  const { data: summary } = useWantedSummary()
  const {
    data: wanted,
    isPending: isLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
  } = useInfiniteWantedItems(typeFilter, statusFilter, subtitleTypeFilter, debouncedSearch, sortBy, sortDir)
  const refreshWanted = useRefreshWanted()
  const updateStatus = useUpdateWantedStatus()
  const processItem = useProcessWantedItem()
  const extractItem = useExtractEmbeddedSub()
  const [extractingItemId, setExtractingItemId] = useState<number | null>(null)
  const [processingItemId, setProcessingItemId] = useState<number | null>(null)
  const retranslateItem = useRetranslateSingle()
  const startBatch = useStartWantedBatch()
  const addBlacklist = useAddToBlacklist()
  const { data: batchStatus } = useWantedBatchStatus()
  const { data: extractStatus, refetch: refetchExtractStatus } = useWantedBatchExtractStatus()
  const { data: probeStatus } = useWantedBatchProbeStatus()
  const startProbe = useStartBatchProbe()
  const cleanupSidecars = useCleanupSidecars()
  const batchTranslate = useBatchTranslate()
  const translationEnabled = useTranslationEnabled()
  const [showCleanupConfirm, setShowCleanupConfirm] = useState(false)
  const queryClient = useQueryClient()

  // Live updates via WebSocket
  useWebSocket({
    onBatchExtractProgress: () => {
      refetchExtractStatus()
    },
    onBatchExtractCompleted: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted-batch-extract-status'] })
      queryClient.invalidateQueries({ queryKey: ['wanted'] })
    },
    onBatchProbeProgress: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted-batch-probe-status'] })
    },
    onBatchProbeCompleted: () => {
      queryClient.invalidateQueries({ queryKey: ['wanted-batch-probe-status'] })
      queryClient.invalidateQueries({ queryKey: ['wanted'] })
    },
    onWantedItemSearched: (raw) => {
      const data = raw as WantedSearchResponse
      setSearchResults((prev) => ({ ...prev, [data.wanted_id]: data }))
      setSearchingItems((prev) => { const next = new Set(prev); next.delete(data.wanted_id); return next })
    },
  })

  // Fallback: invalidate wanted list when polling detects running → false transition
  const prevExtractRunning = useRef<boolean | undefined>(undefined)
  useEffect(() => {
    if (prevExtractRunning.current === true && extractStatus?.running === false) {
      queryClient.invalidateQueries({ queryKey: ['wanted'] })
    }
    prevExtractRunning.current = extractStatus?.running
  }, [extractStatus?.running, queryClient])

  const prevProbeRunning = useRef<boolean | undefined>(undefined)
  useEffect(() => {
    if (prevProbeRunning.current === true && probeStatus?.running === false) {
      queryClient.invalidateQueries({ queryKey: ['wanted'] })
    }
    prevProbeRunning.current = probeStatus?.running
  }, [probeStatus?.running, queryClient])

  const totalWanted = summary?.by_status?.wanted ?? 0
  const totalEpisodes = summary?.by_type?.episode ?? 0
  const totalMovies = summary?.by_type?.movie ?? 0
  const upgradeable = summary?.upgradeable ?? 0
  const forcedCount = summary?.by_subtitle_type?.forced ?? 0

  // Flatten all loaded pages into a single array
  const wantedData = useMemo(
    () => wanted?.pages.flatMap((p) => p.data) ?? [],
    [wanted?.pages]
  )

  // Extract unique languages from loaded data
  const availableLanguages = useMemo(() => {
    const langs = new Set<string>()
    for (const item of wantedData) {
      if (item.target_language) langs.add(item.target_language)
    }
    return Array.from(langs).sort()
  }, [wantedData])

  // Client-side post-filters (upgrade + language have no server-side param)
  const filteredData = useMemo(() => {
    let data = wantedData
    if (upgradeFilter) {
      data = data.filter((item) => item.upgrade_candidate === 1)
    }
    if (languageFilter) {
      data = data.filter((item) => item.target_language === languageFilter)
    }
    return data
  }, [wantedData, upgradeFilter, languageFilter])

  // Group filtered flat items by file_path for grouped row display
  const filteredGroups = useMemo(() => groupByFilePath(filteredData), [filteredData])

  // Infinite scroll sentinel
  const sentinelRef = useRef<HTMLTableRowElement>(null)
  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage()
        }
      },
      { threshold: 0.1 }
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  // Bulk selection helpers
  const visibleIds = useMemo(
    () => filteredGroups.flatMap((g) => g.languages.map((l) => l.id)),
    [filteredGroups]
  )
  const allSelected = visibleIds.length > 0 && visibleIds.every((id) => isSelected(id))
  const someSelected = visibleIds.some((id) => isSelected(id))

  const toggleSelectAll = useCallback(() => {
    if (allSelected) {
      clearSelection(SCOPE)
    } else {
      selectAll(SCOPE, visibleIds)
    }
  }, [allSelected, visibleIds, clearSelection, selectAll])

  const handleToggleGroup = useCallback(
    (itemIds: number[], _shiftKey: boolean) => {
      const allSel = itemIds.every((id) => isSelected(id))
      if (allSel) {
        for (const id of itemIds) {
          const idx = visibleIds.indexOf(id)
          toggleItem(SCOPE, id, idx, false, visibleIds)
        }
      } else {
        for (const id of itemIds) {
          if (!isSelected(id)) {
            const idx = visibleIds.indexOf(id)
            toggleItem(SCOPE, id, idx, false, visibleIds)
          }
        }
      }
    },
    [isSelected, toggleItem, visibleIds]
  )

  const handleFiltersChange = useCallback((filters: ActiveFilter[]) => {
    setActiveFilters(filters)
    const statusVal = filters.find(f => f.key === 'status')?.value
    setStatusFilter(statusVal)
    const typeVal = filters.find(f => f.key === 'item_type')?.value
    setTypeFilter(typeVal)
    const subTypeVal = filters.find(f => f.key === 'subtitle_type')?.value
    setSubtitleTypeFilter(subTypeVal)
    const titleVal = filters.find(f => f.key === 'title')?.value
    setSearchText(titleVal ?? '')
  }, [])

  const handleProcess = (itemId: number) => {
    setProcessingItemId(itemId)
    processItem.mutate(itemId, {
      onSuccess: () => toast('Suche gestartet…', 'success'),
      onError: (e: Error) => toast(e.message, 'error'),
      onSettled: () => setProcessingItemId(null),
    })
  }

  const handleExtract = (itemId: number, targetLanguage?: string) => {
    setExtractingItemId(itemId)
    extractItem.mutate(
      { itemId, options: { target_language: targetLanguage } },
      {
        onSuccess: (data) => {
          toast(`Extracted ${data.format.toUpperCase()} subtitle to ${data.output_path}`, 'success')
        },
        onError: (error: Error) => {
          toast(`Extraction failed: ${error.message}`, 'error')
        },
        onSettled: () => {
          setExtractingItemId(null)
        },
      }
    )
  }

  const handleBatchSearch = () => {
    startBatch.mutate(undefined)
  }

  const handleCleanup = () => {
    cleanupSidecars.mutate(undefined, {
      onSuccess: (result) => {
        toast(t('wanted.cleanup_result', { count: result.deleted.length }), 'success')
        if (result.errors.length) {
          toast(`${result.errors.length} error(s) during cleanup`, 'error')
        }
        setShowCleanupConfirm(false)
      },
      onError: (e: Error) => {
        toast(`Cleanup failed: ${e.message}`, 'error')
        setShowCleanupConfirm(false)
      },
    })
  }

  return (
    <div className="flex flex-col gap-5" style={{ height: 'calc(100vh - 108px)' }}>
      <PageHeader
        title={t('wanted.page_title', 'Wanted')}
        subtitle={t('wanted.page_subtitle', 'Subtitles missing from your library')}
      />

      {/* Batch Probe Progress Banner */}
      {probeStatus?.running && (
        <div
          className="rounded-lg p-4"
          style={{ backgroundColor: 'var(--accent-bg)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--accent)' }}>
              <Loader2 size={14} className="animate-spin" />
              {probeStatus.current_item
                ? `Scanning: ${probeStatus.current_item}`
                : t('wanted.starting', 'Starting...')}
            </div>
            <span className="text-xs tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>
              {probeStatus.processed}/{probeStatus.total}
            </span>
          </div>
          <div className="w-full rounded-full h-2" style={{ backgroundColor: 'var(--border)' }}>
            <div
              className="h-2 rounded-full transition-all duration-300"
              style={{
                width: probeStatus.total > 0 ? `${(probeStatus.processed / probeStatus.total) * 100}%` : '0%',
                backgroundColor: 'var(--accent)',
              }}
            />
          </div>
          <div className="flex gap-4 mt-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
            <span>Ziel: {probeStatus.found}</span>
            <span>Quelle: {probeStatus.extracted}</span>
            <span>{t('wanted.skipped', 'Skipped')}: {probeStatus.skipped}</span>
            <span>{t('wanted.failed', 'Failed')}: {probeStatus.failed}</span>
          </div>
        </div>
      )}

      {/* Batch Extract Progress Banner */}
      {extractStatus?.running && (
        <div
          className="rounded-lg p-4"
          style={{ backgroundColor: 'var(--accent-bg)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--accent)' }}>
              <Loader2 size={14} className="animate-spin" />
              {t('wanted.extracting', { item: extractStatus.current_item || t('wanted.starting') })}
            </div>
            <span className="text-xs tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>
              {extractStatus.processed}/{extractStatus.total}
            </span>
          </div>
          <div className="w-full rounded-full h-2" style={{ backgroundColor: 'var(--border)' }}>
            <div
              className="h-2 rounded-full transition-all duration-300"
              style={{
                width: extractStatus.total > 0 ? `${(extractStatus.processed / extractStatus.total) * 100}%` : '0%',
                backgroundColor: 'var(--accent)',
              }}
            />
          </div>
          <div className="flex gap-4 mt-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
            <span>{t('wanted.succeeded', 'Succeeded')}: {extractStatus.succeeded}</span>
            <span>{t('wanted.failed')}: {extractStatus.failed}</span>
            {(extractStatus.skipped ?? 0) > 0 && (
              <span>{t('wanted.skipped', 'Skipped')}: {extractStatus.skipped}</span>
            )}
          </div>
        </div>
      )}

      {/* Batch Progress Banner */}
      {batchStatus?.running && (
        <div
          className="rounded-lg p-4"
          style={{ backgroundColor: 'var(--accent-bg)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--accent)' }}>
              <Loader2 size={14} className="animate-spin" />
              {t('wanted.processing', { item: batchStatus.current_item || t('wanted.starting') })}
            </div>
            <span className="text-xs tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>
              {batchStatus.processed}/{batchStatus.total}
            </span>
          </div>
          <div className="w-full rounded-full h-2" style={{ backgroundColor: 'var(--border)' }}>
            <div
              className="h-2 rounded-full transition-all duration-300"
              style={{
                width: batchStatus.total > 0 ? `${(batchStatus.processed / batchStatus.total) * 100}%` : '0%',
                backgroundColor: 'var(--accent)',
              }}
            />
          </div>
          <div className="flex gap-4 mt-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
            <span>{t('wanted.found')}: {batchStatus.found}</span>
            <span>{t('wanted.failed')}: {batchStatus.failed}</span>
            <span>{t('wanted.skipped')}: {batchStatus.skipped}</span>
          </div>
        </div>
      )}

      {/* Toolbar: Title + Action Buttons */}
      <WantedToolbar
        summaryTotal={summary?.total ?? 0}
        scanRunning={summary?.scan_running}
        batchRunning={batchStatus?.running}
        startBatchPending={startBatch.isPending}
        refreshPending={refreshWanted.isPending}
        startProbePending={startProbe.isPending}
        probeRunning={probeStatus?.running}
        cleanupPending={cleanupSidecars.isPending}
        batchTranslatePending={batchTranslate.isPending}
        translationEnabled={!!translationEnabled}
        onRefresh={() => refreshWanted.mutate(undefined)}
        onBatchSearch={handleBatchSearch}
        onStartProbe={() => startProbe.mutate(undefined)}
        onShowCleanupConfirm={() => setShowCleanupConfirm(true)}
        onBatchTranslate={() => batchTranslate.mutate([])}
      />

      {/* Filter Panel: Summary Cards + Filters + Search + Sort + FilterBar */}
      <WantedFilterPanel
        scope={SCOPE}
        wantedFilters={wantedFilters}
        totalWanted={totalWanted}
        totalEpisodes={totalEpisodes}
        totalMovies={totalMovies}
        upgradeable={upgradeable}
        forcedCount={forcedCount}
        statusFilter={statusFilter}
        typeFilter={typeFilter}
        subtitleTypeFilter={subtitleTypeFilter}
        upgradeFilter={upgradeFilter}
        languageFilter={languageFilter}
        availableLanguages={availableLanguages}
        activeFilters={activeFilters}
        sortBy={sortBy}
        sortDir={sortDir}
        searchText={searchText}
        onStatusFilter={setStatusFilter}
        onTypeFilter={setTypeFilter}
        onSubtitleTypeFilter={setSubtitleTypeFilter}
        onUpgradeFilter={setUpgradeFilter}
        onLanguageFilter={setLanguageFilter}
        onFiltersChange={handleFiltersChange}
        onSortBy={setSortBy}
        onSortDir={setSortDir}
        onSearchText={setSearchText}
      />

      {/* Table */}
      <div
        data-testid="wanted-list"
        className="rounded-lg overflow-hidden flex-1 min-h-0 flex flex-col"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="flex-1 min-h-0" style={{ overflowY: 'auto' }}>
          <table className="w-full min-w-[800px]">
            <thead style={{ position: 'sticky', top: 0, zIndex: 1, backgroundColor: 'var(--bg-elevated)' }}>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th scope="col" className="text-left px-3 py-2.5 w-8">
                  <button onClick={toggleSelectAll} className="p-0.5" style={{ color: 'var(--text-muted)' }}>
                    {allSelected ? (
                      <CheckSquare size={14} style={{ color: 'var(--accent)' }} />
                    ) : someSelected ? (
                      <MinusSquare size={14} style={{ color: 'var(--accent)' }} />
                    ) : (
                      <Square size={14} />
                    )}
                  </button>
                </th>
                <th scope="col" className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('wanted.title_col')}</th>
                <th scope="col" className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('wanted.se_col')}</th>
                <th scope="col" className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('wanted.status_col')}</th>
                <th scope="col" className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>{t('wanted.existing_col')}</th>
                <th scope="col" className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden md:table-cell" style={{ color: 'var(--text-muted)' }}>{t('wanted.searches_col')}</th>
                <th scope="col" className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden lg:table-cell" style={{ color: 'var(--text-muted)' }}>{t('wanted.last_search_col')}</th>
                <th scope="col" className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden lg:table-cell" style={{ color: 'var(--text-muted)' }}>{t('wanted.added_col')}</th>
                <th scope="col" className="text-right text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)', position: 'sticky', right: 0, zIndex: 2, backgroundColor: 'var(--bg-elevated)' }}>{t('wanted.actions_col')}</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="px-3 py-3"><div className="skeleton h-4 w-4 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-4 w-48 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-4 w-14 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-5 w-20 rounded-full" /></td>
                    <td className="px-3 py-3 hidden sm:table-cell"><div className="skeleton h-4 w-10 rounded" /></td>
                    <td className="px-3 py-3 hidden md:table-cell"><div className="skeleton h-4 w-8 rounded" /></td>
                    <td className="px-3 py-3 hidden lg:table-cell"><div className="skeleton h-4 w-14 rounded" /></td>
                    <td className="px-3 py-3 hidden lg:table-cell"><div className="skeleton h-4 w-14 rounded" /></td>
                    <td className="px-4 py-3"><div className="skeleton h-6 w-6 rounded ml-auto" /></td>
                  </tr>
                ))
              ) : filteredGroups.length ? (
                <>
                  {filteredGroups.map((group, i) => (
                    <WantedGroupedRow
                      key={group.key}
                      group={group}
                      groupIndex={i}
                      expandedItem={expandedItem}
                      sourceLanguage={sourceLanguage}
                      searchingItems={searchingItems}
                      searchResults={searchResults}
                      extractingItemId={extractingItemId}
                      processPending={processItem.isPending}
                      retranslatePending={retranslateItem.isPending}
                      translationEnabled={!!translationEnabled}
                      processingItemId={processingItemId}
                      isSelected={isSelected}
                      onToggleGroup={handleToggleGroup}
                      onExpand={(id) => setExpandedItem(id)}
                      onProcess={handleProcess}
                      onExtract={handleExtract}
                      onRetranslate={(id) => retranslateItem.mutate(id)}
                      onUpdateStatus={(id, status) => updateStatus.mutate({ itemId: id, status })}
                      onPreview={setPreviewFilePath}
                      onInteractiveSearch={setInteractiveItem}
                      onBlacklist={(itemId, providerName, subtitleId, language) => {
                        const item = wantedData.find(d => d.id === itemId)
                        addBlacklist.mutate({
                          provider_name: providerName,
                          subtitle_id: subtitleId,
                          language,
                          title: item?.title ?? '',
                          file_path: item?.file_path ?? '',
                          reason: 'Blacklisted from wanted search',
                        })
                      }}
                    />
                  ))}
                  {isFetchingNextPage && (
                    <tr>
                      <td colSpan={9} className="px-3 py-3 text-center">
                        <Loader2 size={16} className="animate-spin mx-auto" style={{ color: 'var(--text-muted)' }} />
                      </td>
                    </tr>
                  )}
                  <tr ref={sentinelRef} aria-hidden="true" />
                </>
              ) : (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
                    {statusFilter || typeFilter || subtitleTypeFilter || languageFilter ? t('wanted.no_match_filters') : t('wanted.no_wanted_items')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Floating BatchActionBar */}
      <BatchActionBar scope={SCOPE} actions={['ignore', 'unignore', 'blacklist', 'export', 'extract', 'translate']} />

      {/* Subtitle Preview Modal */}
      {previewFilePath && (
        <SubtitleEditorModal
          filePath={previewFilePath}
          initialMode="preview"
          onClose={() => setPreviewFilePath(null)}
        />
      )}

      {/* Interactive Search Modal */}
      <InteractiveSearchModal
        open={!!interactiveItem}
        itemId={interactiveItem?.id}
        itemTitle={interactiveItem?.title ?? ''}
        onClose={() => setInteractiveItem(null)}
        onDownloaded={() => setInteractiveItem(null)}
      />

      {/* Cleanup Sidecars Confirmation Dialog */}
      {showCleanupConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          onClick={() => setShowCleanupConfirm(false)}
        >
          <div
            className="rounded-lg p-6 max-w-md w-full mx-4 space-y-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-base font-semibold">{t('wanted.cleanup')}</h2>
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              {t('wanted.cleanup_confirm')}
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowCleanupConfirm(false)}
                className="px-4 py-2 rounded-md text-sm font-medium"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
              >
                {t('actions.cancel', { ns: 'common' })}
              </button>
              <button
                onClick={handleCleanup}
                disabled={cleanupSidecars.isPending}
                className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-white hover:opacity-90"
                style={{ backgroundColor: 'var(--error)' }}
              >
                {cleanupSidecars.isPending ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                {t('wanted.cleanup')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
