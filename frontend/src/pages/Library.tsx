import { useState, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useLibrary, useLanguageProfiles, useAssignProfile } from '@/hooks/useApi'
import { FilterPresetMenu } from '@/components/filters/FilterPresetMenu'
import type { SeriesInfo, MovieInfo, SyncBatchProgress, SyncBatchComplete, FilterGroup } from '@/lib/types'
import { Tv, Film, Loader2, Settings, ChevronLeft, ChevronRight, Search, RefreshCw, X, LayoutGrid, List } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { autoSyncBulk, startSeriesBatchSearch } from '@/api/client'
import { useWebSocket } from '@/hooks/useWebSocket'
import { toast } from '@/components/shared/Toast'
import { LibraryGridCard } from '@/components/library/LibraryGridCard'
import { VirtualLibraryTable } from '@/components/library/VirtualLibraryTable'

type Tab = 'series' | 'movies'
type SortKey = 'title' | 'missing' | 'episodes'
type SortDir = 'asc' | 'desc'

function Pagination({ page, totalPages, total, pageSize, onPageChange, t }: {
  page: number
  totalPages: number
  total: number
  pageSize: number
  onPageChange: (p: number) => void
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  const start = (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, total)

  const pages: (number | '...')[] = []
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i)
  } else {
    pages.push(1)
    if (page > 3) pages.push('...')
    for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) {
      pages.push(i)
    }
    if (page < totalPages - 2) pages.push('...')
    pages.push(totalPages)
  }

  return (
    <div className="flex items-center justify-between flex-wrap gap-3 mt-3">
      <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
        {t('pagination.show', { start, end, total })}
      </span>
      <div className="flex items-center gap-1">
        <button
          data-testid="pagination-prev"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="p-1.5 rounded-md transition-colors disabled:opacity-30"
          style={{ color: 'var(--text-secondary)' }}
        >
          <ChevronLeft size={14} />
        </button>
        {pages.map((p, i) =>
          p === '...' ? (
            <span key={`dots-${i}`} className="px-1 text-xs" style={{ color: 'var(--text-muted)' }}>...</span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p as number)}
              className="min-w-[28px] h-7 rounded-md text-xs font-medium transition-all"
              style={{
                backgroundColor: p === page ? 'var(--accent)' : 'var(--bg-surface)',
                color: p === page ? '#fff' : 'var(--text-secondary)',
                border: `1px solid ${p === page ? 'var(--accent)' : 'var(--border)'}`,
              }}
            >
              {p}
            </button>
          )
        )}
        <button
          data-testid="pagination-next"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="p-1.5 rounded-md transition-colors disabled:opacity-30"
          style={{ color: 'var(--text-secondary)' }}
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  )
}


// ─── Bulk Sync Panel ──────────────────────────────────────────────────────────

interface SyncState {
  isRunning: boolean
  current: number
  total: number
  completed: number
  failed: number
  filePath: string
}

const INITIAL_SYNC_STATE: SyncState = {
  isRunning: false,
  current: 0,
  total: 0,
  completed: 0,
  failed: 0,
  filePath: '',
}

function BulkSyncPanel({
  series,
  onProgress,
  onComplete,
}: {
  series: SeriesInfo[]
  onProgress: (d: SyncBatchProgress) => void
  onComplete: (d: SyncBatchComplete) => void
}) {
  const [scope, setScope] = useState<'series' | 'library'>('library')
  const [selectedSeriesId, setSelectedSeriesId] = useState<number | ''>('')
  const [engine, setEngine] = useState<'' | 'alass' | 'ffsubsync'>('')
  const [loading, setLoading] = useState(false)
  const [syncState, setSyncState] = useState<SyncState>(INITIAL_SYNC_STATE)

  useWebSocket({
    onSyncBatchProgress: (d) => {
      setSyncState({
        isRunning: true,
        current: d.current,
        total: d.total,
        completed: d.completed,
        failed: d.failed,
        filePath: d.file_path,
      })
      onProgress(d)
    },
    onSyncBatchComplete: (d) => {
      setSyncState((prev) => ({ ...prev, isRunning: false }))
      toast(`Bulk sync complete: ${d.completed} synced, ${d.failed} failed`)
      onComplete(d)
    },
  })

  const handleStart = async () => {
    if (scope === 'series' && !selectedSeriesId) {
      toast('Select a series first', 'error')
      return
    }
    setLoading(true)
    try {
      const res = await autoSyncBulk(
        scope,
        scope === 'series' ? Number(selectedSeriesId) : undefined,
        engine || undefined,
      )
      setSyncState({ ...INITIAL_SYNC_STATE, isRunning: true, total: res.total_items })
      toast(`Bulk sync started: ${res.total_items} files`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Bulk sync failed'
      toast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }

  const pct = syncState.total > 0 ? Math.round((syncState.current / syncState.total) * 100) : 0

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-2">
        <RefreshCw size={14} style={{ color: 'var(--accent)' }} />
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          Bulk Auto-Sync
        </span>
        {syncState.isRunning && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded font-medium animate-pulse"
            style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
          >
            Running
          </span>
        )}
      </div>

      {/* Controls */}
      {!syncState.isRunning && (
        <div className="flex flex-wrap items-center gap-2">
          {/* Scope */}
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as 'series' | 'library')}
            className="text-xs px-2 py-1.5 rounded cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border)',
            }}
          >
            <option value="library">Entire Library</option>
            <option value="series">Single Series</option>
          </select>

          {/* Series picker */}
          {scope === 'series' && (
            <select
              value={selectedSeriesId}
              onChange={(e) => setSelectedSeriesId(e.target.value === '' ? '' : Number(e.target.value))}
              className="text-xs px-2 py-1.5 rounded cursor-pointer max-w-[200px]"
              style={{
                backgroundColor: 'var(--bg-primary)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
              }}
            >
              <option value="">-- Select series --</option>
              {series.map((s) => (
                <option key={s.id} value={s.id}>{s.title}</option>
              ))}
            </select>
          )}

          {/* Engine override */}
          <select
            value={engine}
            onChange={(e) => setEngine(e.target.value as '' | 'alass' | 'ffsubsync')}
            className="text-xs px-2 py-1.5 rounded cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border)',
            }}
          >
            <option value="">Default engine</option>
            <option value="alass">alass</option>
            <option value="ffsubsync">ffsubsync</option>
          </select>

          <button
            onClick={() => { void handleStart() }}
            disabled={loading || (scope === 'series' && !selectedSeriesId)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white disabled:opacity-50"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            Start Bulk Sync
          </button>
        </div>
      )}

      {/* Progress */}
      {syncState.isRunning && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs" style={{ color: 'var(--text-secondary)' }}>
            <span>
              {syncState.current}/{syncState.total} &nbsp;&mdash;&nbsp;
              <span style={{ color: 'var(--success)' }}>{syncState.completed} synced</span>
              {syncState.failed > 0 && (
                <> &nbsp;/&nbsp; <span style={{ color: 'var(--error)' }}>{syncState.failed} failed</span></>
              )}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>{pct}%</span>
          </div>
          <div
            className="h-2 rounded overflow-hidden"
            style={{ backgroundColor: 'var(--bg-primary)' }}
          >
            <div
              className="h-full rounded transition-all duration-500"
              style={{ width: `${pct}%`, backgroundColor: 'var(--accent)' }}
            />
          </div>
          {syncState.filePath && (
            <p
              className="text-[11px] truncate"
              style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
              title={syncState.filePath}
            >
              {syncState.filePath.replaceAll("\\", "/").split("/").slice(-2).join("/")}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export function LibraryPage() {
  const { t } = useTranslation('library')
  const { data: library, isLoading } = useLibrary()
  const { data: profiles } = useLanguageProfiles()
  const assignProfile = useAssignProfile()
  const [activeTab, setActiveTab] = useState<Tab>('series')
  const [gridPage, setGridPage] = useState(1)
  const [searchQuery, setSearchQuery] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('title')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [showBulkSync, setShowBulkSync] = useState(false)
  const [selectedSeries, setSelectedSeries] = useState<Set<number>>(new Set())
  const [viewMode, setViewMode] = useState<'table' | 'grid'>(() =>
    (localStorage.getItem('library_view_mode') as 'table' | 'grid') ?? 'table'
  )
  const [statusFilter, setStatusFilter] = useState<'all' | 'missing' | 'complete'>('all')
  const [profileFilter, setProfileFilter] = useState<string>('all')
  const navigate = useNavigate()

  const handleViewMode = (mode: 'table' | 'grid') => {
    setViewMode(mode)
    localStorage.setItem('library_view_mode', mode)
  }

  const toggleSeries = useCallback((id: number) => {
    setSelectedSeries(prev => {
      const next = new Set(prev)
      if (next.has(id)) { next.delete(id) } else { next.add(id) }
      return next
    })
  }, [])

  const clearSelection = useCallback(() => setSelectedSeries(new Set()), [])

  // Sync batch callbacks (unused beyond triggering toast in BulkSyncPanel)
  const handleSyncProgress = useCallback((_d: SyncBatchProgress) => {}, [])
  const handleSyncComplete = useCallback((_d: SyncBatchComplete) => {}, [])

  const handleSort = useCallback((key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir(key === 'missing' ? 'desc' : 'asc')
    }
    setGridPage(1)
  }, [sortKey])

  const handleProfileChange = useCallback((seriesId: number, profileId: number) => {
    assignProfile.mutate({ type: 'series', arrId: seriesId, profileId })
  }, [assignProfile])

  // Filter + sort
  const processedItems = useMemo(() => {
    const series = library?.series || []
    const movies = library?.movies || []
    let items: (SeriesInfo | MovieInfo)[] = activeTab === 'series' ? [...series] : [...movies]

    // Search filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      items = items.filter((item) => item.title.toLowerCase().includes(q))
    }

    // Status filter (series only)
    if (activeTab === 'series' && statusFilter !== 'all') {
      items = items.filter((item) => {
        const missing = (item as SeriesInfo).missing_count ?? 0
        return statusFilter === 'missing' ? missing > 0 : missing === 0
      })
    }

    // Profile filter (series only)
    if (activeTab === 'series' && profileFilter !== 'all') {
      items = items.filter((item) => (item as SeriesInfo).profile_name === profileFilter)
    }

    // Sort
    items.sort((a, b) => {
      let cmp = 0
      if (sortKey === 'title') {
        cmp = a.title.localeCompare(b.title)
      } else if (sortKey === 'missing' && activeTab === 'series') {
        cmp = ((a as SeriesInfo).missing_count ?? 0) - ((b as SeriesInfo).missing_count ?? 0)
      } else if (sortKey === 'episodes' && activeTab === 'series') {
        const aPct = (a as SeriesInfo).episodes > 0
          ? (a as SeriesInfo).episodes_with_files / (a as SeriesInfo).episodes
          : 0
        const bPct = (b as SeriesInfo).episodes > 0
          ? (b as SeriesInfo).episodes_with_files / (b as SeriesInfo).episodes
          : 0
        cmp = aPct - bPct
      }
      return sortDir === 'asc' ? cmp : -cmp
    })

    return items
  }, [library, activeTab, searchQuery, sortKey, sortDir, statusFilter, profileFilter])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  const series = library?.series || []
  const movies = library?.movies || []
  const isEmpty = series.length === 0 && movies.length === 0

  // Grid pagination
  const GRID_PAGE_SIZE = 25
  const gridTotalPages = Math.ceil(processedItems.length / GRID_PAGE_SIZE)
  const gridCurrentPage = Math.min(gridPage, gridTotalPages || 1)
  const gridItems = processedItems.slice(
    (gridCurrentPage - 1) * GRID_PAGE_SIZE,
    gridCurrentPage * GRID_PAGE_SIZE,
  )

  // Reset page on tab change
  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab)
    setGridPage(1)
    setSearchQuery('')
  }

  const handleRowClick = (id: number) => {
    if (activeTab === 'series') {
      navigate(`/library/series/${id}`)
    }
  }

  if (isEmpty) {
    return (
      <div className="space-y-5">
        <h1>{t('title')}</h1>
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
          <h2 className="text-base font-semibold mb-2">{t('empty.title')}</h2>
          <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
            {t('empty.message')}
          </p>
          <button
            onClick={() => navigate('/settings')}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-white hover:opacity-90"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            <Settings size={14} />
            {t('empty.go_to_settings')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1>{t('title')}</h1>
        <div className="flex items-center gap-3">
          {/* Search Input */}
          <div className="relative">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
              style={{ color: 'var(--text-muted)' }}
            />
            <input
              data-testid="library-search"
              type="text"
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); setGridPage(1) }}
              placeholder={t('search_placeholder')}
              className="pl-8 pr-3 py-1.5 rounded-md text-xs w-48 focus:outline-none transition-all"
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
          {/* Tabs */}
          <div className="flex gap-1.5">
            <button
              data-testid="tab-series"
              onClick={() => handleTabChange('series')}
              className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
              style={{
                backgroundColor: activeTab === 'series' ? 'var(--accent-bg)' : 'var(--bg-surface)',
                color: activeTab === 'series' ? 'var(--accent)' : 'var(--text-secondary)',
                border: `1px solid ${activeTab === 'series' ? 'var(--accent-dim)' : 'var(--border)'}`,
              }}
            >
              <Tv size={12} />
              {t('series_tab', { count: series.length })}
            </button>
            <button
              data-testid="tab-movies"
              onClick={() => handleTabChange('movies')}
              className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
              style={{
                backgroundColor: activeTab === 'movies' ? 'var(--accent-bg)' : 'var(--bg-surface)',
                color: activeTab === 'movies' ? 'var(--accent)' : 'var(--text-secondary)',
                border: `1px solid ${activeTab === 'movies' ? 'var(--accent-dim)' : 'var(--border)'}`,
              }}
            >
              <Film size={12} />
              {t('movies_tab', { count: movies.length })}
            </button>
          </div>

          {/* Status filter (series only) */}
          {activeTab === 'series' && (
            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value as typeof statusFilter); setGridPage(1) }}
              className="px-2 py-1.5 rounded-md text-xs"
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
              }}
            >
              <option value="all">{t('filter_status_all')}</option>
              <option value="missing">{t('filter_status_missing')}</option>
              <option value="complete">{t('filter_status_complete')}</option>
            </select>
          )}

          {/* Profile filter (series only) */}
          {activeTab === 'series' && profiles && profiles.length > 0 && (
            <select
              value={profileFilter}
              onChange={(e) => { setProfileFilter(e.target.value); setGridPage(1) }}
              className="px-2 py-1.5 rounded-md text-xs"
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
              }}
            >
              <option value="all">{t('filter_profile_all')}</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.name}>{p.name}</option>
              ))}
            </select>
          )}

          {/* Filter Preset Menu */}
          {activeTab === 'series' && (
            <FilterPresetMenu
              scope="library"
              activeFilters={[
                ...(statusFilter !== 'all' ? [{ key: 'status', op: 'eq', value: statusFilter }] : []),
                ...(profileFilter !== 'all' ? [{ key: 'profile', op: 'eq', value: profileFilter }] : []),
              ]}
              onPresetLoad={(conditions: FilterGroup) => {
                if (conditions.logic === 'AND') {
                  conditions.conditions.forEach((cond) => {
                    if ('field' in cond && 'value' in cond) {
                      if (cond.field === 'status') setStatusFilter(String(cond.value) as 'all' | 'missing' | 'complete')
                      if (cond.field === 'profile') setProfileFilter(String(cond.value))
                    }
                  })
                }
              }}
            />
          )}

          {/* View toggle */}
          <div
            className="flex rounded-md overflow-hidden"
            style={{ border: '1px solid var(--border)' }}
          >
            <button
              onClick={() => handleViewMode('table')}
              className="px-2.5 py-1.5 transition-colors"
              style={{
                backgroundColor: viewMode === 'table' ? 'var(--accent-bg)' : 'var(--bg-surface)',
                color: viewMode === 'table' ? 'var(--accent)' : 'var(--text-muted)',
              }}
              title={t('view_table')}
            >
              <List size={14} />
            </button>
            <button
              onClick={() => handleViewMode('grid')}
              className="px-2.5 py-1.5 transition-colors"
              style={{
                backgroundColor: viewMode === 'grid' ? 'var(--accent-bg)' : 'var(--bg-surface)',
                color: viewMode === 'grid' ? 'var(--accent)' : 'var(--text-muted)',
                borderLeft: '1px solid var(--border)',
              }}
              title={t('view_grid')}
            >
              <LayoutGrid size={14} />
            </button>
          </div>

          {/* Bulk Sync toggle */}
          <button
            onClick={() => setShowBulkSync((v) => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
            style={{
              backgroundColor: showBulkSync ? 'var(--accent-bg)' : 'var(--bg-surface)',
              color: showBulkSync ? 'var(--accent)' : 'var(--text-secondary)',
              border: `1px solid ${showBulkSync ? 'var(--accent-dim)' : 'var(--border)'}`,
            }}
          >
            {showBulkSync ? <X size={12} /> : <RefreshCw size={12} />}
            Auto-Sync
          </button>
        </div>
      </div>

      {/* Bulk Sync Panel */}
      {showBulkSync && (
        <BulkSyncPanel
          series={library?.series || []}
          onProgress={handleSyncProgress}
          onComplete={handleSyncComplete}
        />
      )}

      {processedItems.length === 0 ? (
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {searchQuery
              ? t('no_results', { query: searchQuery })
              : t('no_items', { type: activeTab, source: activeTab === 'series' ? 'Sonarr' : 'Radarr' })}
          </p>
        </div>
      ) : (
        <>
          {activeTab === 'series' && selectedSeries.size > 0 && (
            <div
              className="flex items-center gap-2 px-4 py-2 rounded-lg mb-3"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--accent-dim)',
              }}
            >
              <span className="text-xs font-medium" style={{ color: 'var(--accent)' }}>
                {selectedSeries.size} series selected
              </span>
              <button
                onClick={async () => {
                  try {
                    await startSeriesBatchSearch([...selectedSeries])
                    toast('Batch search queued')
                    clearSelection()
                  } catch (err) {
                    console.error('Batch search failed:', err)
                    toast('Batch search failed', 'error')
                  }
                }}
                className="px-3 py-1.5 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
              >
                Search All Missing
              </button>
              <button
                onClick={clearSelection}
                className="ml-auto px-2 py-1 rounded text-xs"
                style={{ color: 'var(--text-muted)' }}
              >
                Clear
              </button>
            </div>
          )}
          {viewMode === 'grid' ? (
            <>
              <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-3">
                {gridItems.map((item, i) => (
                  <LibraryGridCard
                    key={item.id}
                    item={item}
                    onClick={() => handleRowClick(item.id)}
                    style={{ animationDelay: `${Math.min(i * 30, 300)}ms` }}
                  />
                ))}
              </div>
              {gridTotalPages > 1 && (
                <Pagination
                  page={gridCurrentPage}
                  totalPages={gridTotalPages}
                  total={processedItems.length}
                  pageSize={GRID_PAGE_SIZE}
                  onPageChange={setGridPage}
                  t={t}
                />
              )}
            </>
          ) : (
            <VirtualLibraryTable
              key={activeTab}
              items={processedItems}
              type={activeTab}
              profiles={profiles || []}
              onRowClick={handleRowClick}
              onProfileChange={handleProfileChange}
              sortKey={sortKey}
              sortDir={sortDir}
              onSort={handleSort}
              t={t}
              selectedSeries={selectedSeries}
              onToggleSeries={toggleSeries}
              onSelectAll={() => setSelectedSeries(new Set(processedItems.map((s) => s.id)))}
              onClearSelection={clearSelection}
            />
          )}
        </>
      )}
    </div>
  )
}
