import { useState, useMemo, useCallback, useEffect, Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useWantedItems, useWantedSummary, useRefreshWanted, useUpdateWantedStatus,
  useSearchWantedItem, useProcessWantedItem, useStartWantedBatch, useWantedBatchStatus,
  useRetranslateSingle, useAddToBlacklist, useExtractEmbeddedSub,
} from '@/hooks/useApi'
import { StatusBadge, SubtitleTypeBadge } from '@/components/shared/StatusBadge'
import { formatRelativeTime, truncatePath } from '@/lib/utils'
import { toast } from '@/components/shared/Toast'
import type { WantedSearchResponse, FilterCondition } from '@/lib/types'
import {
  RefreshCw, ChevronLeft, ChevronRight, Search, Film, Tv,
  ArrowUpCircle, EyeOff, Eye, Play, Loader2, ChevronUp, Ban,
  CheckSquare, Square, MinusSquare, Download, ArrowUp, ArrowDown, ScanSearch,
} from 'lucide-react'
import SubtitleEditorModal from '@/components/editor/SubtitleEditorModal'
import { InteractiveSearchModal } from '@/components/wanted/InteractiveSearchModal'
import { FilterBar } from '@/components/filters/FilterBar'
import type { FilterDef, ActiveFilter } from '@/components/filters/FilterBar'
import { BatchActionBar } from '@/components/batch/BatchActionBar'
import { useSelectionStore } from '@/stores/selectionStore'

/** Derive subtitle file path from media path + language + format. */
function deriveSubtitlePath(mediaPath: string, lang: string, format: string): string {
  const lastDot = mediaPath.lastIndexOf('.')
  const base = lastDot > 0 ? mediaPath.substring(0, lastDot) : mediaPath
  return `${base}.${lang}.${format}`
}

const STATUS_FILTERS = ['all', 'wanted', 'failed', 'ignored'] as const
const TYPE_FILTERS = ['all', 'episode', 'movie'] as const
const SUBTITLE_TYPE_FILTERS = ['all', 'full', 'forced'] as const

const SCOPE = 'wanted' as const

const WANTED_FILTERS: FilterDef[] = [
  { key: 'status', label: 'Status', type: 'select' as const, options: [
    { value: 'wanted', label: 'Wanted' },
    { value: 'ignored', label: 'Ignored' },
    { value: 'failed', label: 'Failed' },
    { value: 'found', label: 'Found' },
  ]},
  { key: 'item_type', label: 'Type', type: 'select' as const, options: [
    { value: 'episode', label: 'Episode' },
    { value: 'movie', label: 'Movie' },
  ]},
  { key: 'subtitle_type', label: 'Subtitle Type', type: 'select' as const, options: [
    { value: 'full', label: 'Full' },
    { value: 'forced', label: 'Forced' },
  ]},
  { key: 'title', label: 'Title', type: 'text' as const },
]

const SORT_FIELDS = [
  { value: 'added_at', labelKey: 'wanted.sortFields.added_at' },
  { value: 'title', labelKey: 'wanted.sortFields.title' },
  { value: 'last_search_at', labelKey: 'wanted.sortFields.last_search_at' },
  { value: 'current_score', labelKey: 'wanted.sortFields.current_score' },
  { value: 'search_count', labelKey: 'wanted.sortFields.search_count' },
] as const

function SummaryCard({ icon: Icon, label, value, color }: {
  icon: typeof Search
  label: string
  value: number
  color: string
}) {
  return (
    <div
      className="rounded-lg p-4 flex items-center gap-3"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div className="p-2 rounded-lg" style={{ backgroundColor: `${color}12` }}>
        <Icon size={18} style={{ color }} />
      </div>
      <div>
        <div className="text-lg font-bold tabular-nums" style={{ fontFamily: 'var(--font-mono)' }}>
          {value}
        </div>
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{label}</div>
      </div>
    </div>
  )
}

function ScoreBadge({ score }: { score: number }) {
  const color = score >= 300 ? 'var(--success)' : score >= 200 ? 'var(--warning)' : 'var(--text-muted)'
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold tabular-nums"
      style={{ backgroundColor: `${color}18`, color, fontFamily: 'var(--font-mono)' }}
    >
      {score}
    </span>
  )
}

function SearchResultsRow({ results, isLoading, onBlacklist, t }: {
  results: WantedSearchResponse | null
  isLoading: boolean
  onBlacklist: (providerName: string, subtitleId: string, language: string) => void
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  if (isLoading) {
    return (
      <tr style={{ backgroundColor: 'var(--bg-primary)' }}>
        <td colSpan={9} className="px-6 py-4">
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
            <Loader2 size={14} className="animate-spin" />
            {t('wanted.searching_providers')}
          </div>
        </td>
      </tr>
    )
  }

  if (!results) return null

  const allResults = [
    ...results.target_results.map((r) => ({ ...r, _type: 'target' as const })),
    ...results.source_results.map((r) => ({ ...r, _type: 'source' as const })),
  ]

  if (allResults.length === 0) {
    return (
      <tr style={{ backgroundColor: 'var(--bg-primary)' }}>
        <td colSpan={9} className="px-6 py-4 text-sm" style={{ color: 'var(--text-muted)' }}>
          {t('wanted.no_results_found')}
        </td>
      </tr>
    )
  }

  return (
    <tr style={{ backgroundColor: 'var(--bg-primary)' }}>
      <td colSpan={9} className="px-4 py-2">
        <div className="rounded-md overflow-hidden" style={{ border: '1px solid var(--border)' }}>
          <table className="w-full">
            <thead>
              <tr style={{ backgroundColor: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Provider</th>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Type</th>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Format</th>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Score</th>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Release</th>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>Lang</th>
                <th className="text-right text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5" style={{ color: 'var(--text-muted)' }}></th>
              </tr>
            </thead>
            <tbody>
              {allResults.map((r, i) => (
                <tr
                  key={`${r.provider}-${r.subtitle_id}-${i}`}
                  style={{ borderBottom: i < allResults.length - 1 ? '1px solid var(--border)' : undefined }}
                >
                  <td className="px-3 py-1.5 text-xs" style={{ fontFamily: 'var(--font-mono)' }}>
                    {r.provider}
                  </td>
                  <td className="px-3 py-1.5">
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded uppercase font-medium"
                      style={{
                        backgroundColor: r._type === 'target' ? 'rgba(16,185,129,0.1)' : 'rgba(29,184,212,0.1)',
                        color: r._type === 'target' ? 'var(--success)' : 'var(--accent)',
                      }}
                    >
                      {r._type === 'target' ? 'Target' : 'Source'}
                    </span>
                  </td>
                  <td className="px-3 py-1.5">
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded uppercase font-bold"
                      style={{
                        backgroundColor: r.format === 'ass' ? 'rgba(16,185,129,0.1)' : 'var(--bg-surface)',
                        color: r.format === 'ass' ? 'var(--success)' : 'var(--text-secondary)',
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {r.format}
                    </span>
                  </td>
                  <td className="px-3 py-1.5">
                    <ScoreBadge score={r.score} />
                  </td>
                  <td className="px-3 py-1.5 text-xs truncate max-w-[200px]" title={r.release_info || r.filename} style={{ color: 'var(--text-secondary)' }}>
                    {r.release_info || r.filename || '-'}
                  </td>
                  <td className="px-3 py-1.5 text-xs uppercase" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                    {r.language}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <button
                      onClick={() => onBlacklist(r.provider, r.subtitle_id, r.language)}
                      className="p-0.5 rounded transition-colors duration-150"
                      title={t('wanted.blacklist_subtitle')}
                      style={{ color: 'var(--text-muted)' }}
                      onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--error)')}
                      onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                    >
                      <Ban size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </td>
    </tr>
  )
}

export function WantedPage() {
  const { t } = useTranslation('library')
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [typeFilter, setTypeFilter] = useState<string | undefined>()
  const [subtitleTypeFilter, setSubtitleTypeFilter] = useState<string | undefined>()
  const [upgradeFilter, setUpgradeFilter] = useState(false)
  const [languageFilter, setLanguageFilter] = useState<string | undefined>()
  const [expandedItem, setExpandedItem] = useState<number | null>(null)
  const [searchResults, setSearchResults] = useState<Record<number, WantedSearchResponse>>({})
  const [previewFilePath, setPreviewFilePath] = useState<string | null>(null)
  const [interactiveItem, setInteractiveItem] = useState<{ id: number; title: string } | null>(null)

  // FilterBar state
  const [activeFilters, setActiveFilters] = useState<ActiveFilter[]>([])
  const [sortBy, setSortBy] = useState('added_at')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [searchText, setSearchText] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchText), 300)
    return () => clearTimeout(timer)
  }, [searchText])

  // Zustand selection store
  const { toggleItem, selectAll, clearSelection, isSelected } = useSelectionStore()
  const { data: summary } = useWantedSummary()
  const { data: wanted, isLoading } = useWantedItems(page, 50, typeFilter, statusFilter, subtitleTypeFilter)
  const refreshWanted = useRefreshWanted()
  const updateStatus = useUpdateWantedStatus()
  const searchItem = useSearchWantedItem()
  const processItem = useProcessWantedItem()
  const extractItem = useExtractEmbeddedSub()
  const retranslateItem = useRetranslateSingle()
  const startBatch = useStartWantedBatch()
  const addBlacklist = useAddToBlacklist()
  const { data: batchStatus } = useWantedBatchStatus()

  const totalWanted = summary?.by_status?.wanted ?? 0
  const totalEpisodes = summary?.by_type?.episode ?? 0
  const totalMovies = summary?.by_type?.movie ?? 0
  const upgradeable = summary?.upgradeable ?? 0
  const forcedCount = summary?.by_subtitle_type?.forced ?? 0

  // Extract unique languages from data
  const wantedData = wanted?.data
  const availableLanguages = useMemo(() => {
    if (!wantedData) return []
    const langs = new Set<string>()
    for (const item of wantedData) {
      if (item.target_language) langs.add(item.target_language)
    }
    return Array.from(langs).sort()
  }, [wantedData])

  // Client-side filters + search + sort
  const filteredData = useMemo(() => {
    let data = wanted?.data
    if (!data) return data
    if (upgradeFilter) {
      data = data.filter((item) => item.upgrade_candidate === 1)
    }
    if (languageFilter) {
      data = data.filter((item) => item.target_language === languageFilter)
    }
    if (debouncedSearch) {
      const q = debouncedSearch.toLowerCase()
      data = data.filter((item) =>
        (item.title && item.title.toLowerCase().includes(q)) ||
        (item.file_path && item.file_path.toLowerCase().includes(q))
      )
    }
    // Client-side sort
    const sorted = [...data]
    sorted.sort((a, b) => {
      let cmp = 0
      if (sortBy === 'title') {
        cmp = (a.title || '').localeCompare(b.title || '')
      } else if (sortBy === 'added_at') {
        cmp = (a.added_at || '').localeCompare(b.added_at || '')
      } else if (sortBy === 'last_search_at') {
        cmp = (a.last_search_at || '').localeCompare(b.last_search_at || '')
      } else if (sortBy === 'current_score') {
        cmp = (a.current_score ?? 0) - (b.current_score ?? 0)
      } else if (sortBy === 'search_count') {
        cmp = (a.search_count ?? 0) - (b.search_count ?? 0)
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
    return sorted
  }, [wanted?.data, upgradeFilter, languageFilter, debouncedSearch, sortBy, sortDir])

  // Bulk selection helpers using Zustand store
  const visibleIds = useMemo(() => filteredData?.map((d) => d.id) ?? [], [filteredData])
  const allSelected = visibleIds.length > 0 && visibleIds.every((id) => isSelected(SCOPE, id))
  const someSelected = visibleIds.some((id) => isSelected(SCOPE, id))

  const toggleSelectAll = useCallback(() => {
    if (allSelected) {
      clearSelection(SCOPE)
    } else {
      selectAll(SCOPE, visibleIds)
    }
  }, [allSelected, visibleIds, clearSelection, selectAll])

  // Handle FilterBar filter changes -- sync relevant filters with existing filter state
  const handleFiltersChange = useCallback((filters: ActiveFilter[]) => {
    setActiveFilters(filters)
    setPage(1)
    // Sync FilterBar selections back to existing filter buttons
    const statusVal = filters.find(f => f.key === 'status')?.value
    setStatusFilter(statusVal)
    const typeVal = filters.find(f => f.key === 'item_type')?.value
    setTypeFilter(typeVal)
    const subTypeVal = filters.find(f => f.key === 'subtitle_type')?.value
    setSubtitleTypeFilter(subTypeVal)
    // Sync title filter from FilterBar into the search text box (C9 fix)
    const titleVal = filters.find(f => f.key === 'title')?.value
    setSearchText(titleVal ?? '')
  }, [])

  const handleSearch = (itemId: number) => {
    if (expandedItem === itemId) {
      setExpandedItem(null)
      return
    }
    setExpandedItem(itemId)
    searchItem.mutate(itemId, {
      onSuccess: (data) => {
        setSearchResults((prev) => ({ ...prev, [itemId]: data }))
      },
    })
  }

  const handleProcess = (itemId: number) => {
    processItem.mutate(itemId, {
      onError: (e: Error) => toast(e.message, 'error'),
    })
  }

  const handleExtract = (itemId: number, targetLanguage?: string) => {
    extractItem.mutate(
      { itemId, options: { target_language: targetLanguage } },
      {
        onSuccess: (data) => {
          toast(`Extracted ${data.format.toUpperCase()} subtitle to ${data.output_path}`, 'success')
        },
        onError: (error: Error) => {
          toast(`Extraction failed: ${error.message}`, 'error')
        },
      }
    )
  }

  const handleBatchSearch = () => {
    startBatch.mutate(undefined)
  }

  return (
    <div className="space-y-5">
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

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1>{t('wanted.title')}</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
            {t('wanted.items_missing', { count: summary?.total ?? 0 })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleBatchSearch}
            disabled={startBatch.isPending || batchStatus?.running}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium hover:opacity-90"
            style={{
              backgroundColor: 'var(--bg-surface)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
            }}
          >
            <Search size={14} />
            {batchStatus?.running ? t('wanted.searching') : t('wanted.search_all')}
          </button>
          <button
            onClick={() => refreshWanted.mutate(undefined)}
            disabled={refreshWanted.isPending || summary?.scan_running}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-white hover:opacity-90"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            <RefreshCw
              size={14}
              className={refreshWanted.isPending || summary?.scan_running ? 'animate-spin' : ''}
            />
            {summary?.scan_running ? t('wanted.scanning') : t('wanted.refresh')}
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <SummaryCard icon={Search} label={t('wanted.total_wanted')} value={totalWanted} color="var(--warning)" />
        <SummaryCard icon={Tv} label={t('wanted.episodes')} value={totalEpisodes} color="var(--accent)" />
        <SummaryCard icon={Film} label={t('wanted.movies')} value={totalMovies} color="var(--text-secondary)" />
        <SummaryCard icon={ArrowUpCircle} label={t('wanted.srt_upgradeable')} value={upgradeable} color="var(--success)" />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex gap-1.5">
          {STATUS_FILTERS.map((s) => {
            const isActive = (s === 'all' && !statusFilter) || statusFilter === s
            return (
              <button
                key={s}
                onClick={() => { setStatusFilter(s === 'all' ? undefined : s); setPage(1) }}
                className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
                style={{
                  backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--bg-surface)',
                  color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                  border: `1px solid ${isActive ? 'var(--accent-dim)' : 'var(--border)'}`,
                }}
              >
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            )
          })}
        </div>
        <div className="flex gap-1.5">
          {TYPE_FILTERS.map((t) => {
            const isActive = (t === 'all' && !typeFilter) || typeFilter === t
            return (
              <button
                key={t}
                onClick={() => { setTypeFilter(t === 'all' ? undefined : t); setPage(1) }}
                className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
                style={{
                  backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--bg-surface)',
                  color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                  border: `1px solid ${isActive ? 'var(--accent-dim)' : 'var(--border)'}`,
                }}
              >
                {t === 'all' ? 'All Types' : t.charAt(0).toUpperCase() + t.slice(1) + 's'}
              </button>
            )
          })}
        </div>
        {forcedCount > 0 && (
          <div className="flex gap-1.5">
            {SUBTITLE_TYPE_FILTERS.map((st) => {
              const isActive = (st === 'all' && !subtitleTypeFilter) || subtitleTypeFilter === st
              return (
                <button
                  key={st}
                  onClick={() => { setSubtitleTypeFilter(st === 'all' ? undefined : st); setPage(1) }}
                  className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
                  style={{
                    backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--bg-surface)',
                    color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                    border: `1px solid ${isActive ? 'var(--accent-dim)' : 'var(--border)'}`,
                  }}
                >
                  {st === 'all' ? 'All Subs' : st.charAt(0).toUpperCase() + st.slice(1)}
                  {st === 'forced' && ` (${forcedCount})`}
                </button>
              )
            })}
          </div>
        )}
        {availableLanguages.length > 1 && (
          <div className="flex gap-1.5">
            <button
              onClick={() => { setLanguageFilter(undefined); setPage(1) }}
              className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
              style={{
                backgroundColor: !languageFilter ? 'var(--accent-bg)' : 'var(--bg-surface)',
                color: !languageFilter ? 'var(--accent)' : 'var(--text-secondary)',
                border: `1px solid ${!languageFilter ? 'var(--accent-dim)' : 'var(--border)'}`,
              }}
            >
              All Langs
            </button>
            {availableLanguages.map((lang) => {
              const isActive = languageFilter === lang
              return (
                <button
                  key={lang}
                  onClick={() => { setLanguageFilter(isActive ? undefined : lang); setPage(1) }}
                  className="px-3 py-1.5 rounded-md text-xs font-medium uppercase transition-all duration-150"
                  style={{
                    backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--bg-surface)',
                    color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                    border: `1px solid ${isActive ? 'var(--accent-dim)' : 'var(--border)'}`,
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {lang}
                </button>
              )
            })}
          </div>
        )}
        {upgradeable > 0 && (
          <button
            onClick={() => { setUpgradeFilter(!upgradeFilter); setPage(1) }}
            className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
            style={{
              backgroundColor: upgradeFilter ? 'rgba(16,185,129,0.1)' : 'var(--bg-surface)',
              color: upgradeFilter ? 'var(--success)' : 'var(--text-secondary)',
              border: `1px solid ${upgradeFilter ? 'var(--success)' : 'var(--border)'}`,
            }}
          >
            Upgrades Only ({upgradeable})
          </button>
        )}
      </div>

      {/* Search + Sort Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
            style={{ color: 'var(--text-muted)' }}
          />
          <input
            type="text"
            placeholder={t('wanted.search_placeholder', 'Search wanted items...')}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="pl-8 pr-3 py-1.5 rounded-md text-xs w-52 focus:outline-none transition-all"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          />
        </div>

        <div className="flex items-center gap-1.5 ml-auto">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {t('wanted.sortBy', 'Sort by')}:
          </span>
          <select
            value={sortBy}
            onChange={(e) => { setSortBy(e.target.value); setPage(1) }}
            className="text-xs px-2 py-1.5 rounded-md cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-surface)',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border)',
            }}
          >
            {SORT_FIELDS.map((f) => (
              <option key={f.value} value={f.value}>{t(f.labelKey, f.value)}</option>
            ))}
          </select>
          <button
            onClick={() => setSortDir((d) => d === 'asc' ? 'desc' : 'asc')}
            className="p-1.5 rounded-md transition-all duration-150"
            title={sortDir === 'asc' ? 'Ascending' : 'Descending'}
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              color: 'var(--accent)',
            }}
          >
            {sortDir === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
          </button>
        </div>
      </div>

      {/* FilterBar */}
      <FilterBar
        scope={SCOPE}
        filters={WANTED_FILTERS}
        activeFilters={activeFilters}
        onFiltersChange={handleFiltersChange}
        onPresetLoad={(conditions) => {
          if (conditions.logic === 'AND') {
            const filters = conditions.conditions
              .filter((c): c is FilterCondition => 'field' in c)
              .map((c) => {
                const def = WANTED_FILTERS.find(f => f.key === c.field)
                return { key: c.field, op: c.op, value: String(c.value), label: def?.label ?? c.field }
              })
            handleFiltersChange(filters)
          }
        }}
      />

      {/* Table */}
      <div
        className="rounded-lg overflow-hidden"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px]">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th className="text-left px-3 py-2.5 w-8">
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
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('wanted.title_col')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('wanted.se_col')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('wanted.status_col')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>{t('wanted.existing_col')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden md:table-cell" style={{ color: 'var(--text-muted)' }}>{t('wanted.searches_col')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden lg:table-cell" style={{ color: 'var(--text-muted)' }}>{t('wanted.last_search_col')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden lg:table-cell" style={{ color: 'var(--text-muted)' }}>{t('wanted.added_col')}</th>
                <th className="text-right text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('wanted.actions_col')}</th>
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
              ) : filteredData?.length ? (
                filteredData.map((item) => (
                  <Fragment key={item.id}>
                    <tr
                      className="transition-colors duration-100"
                      style={{ borderBottom: '1px solid var(--border)' }}
                      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)')}
                      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                    >
                      <td className="px-3 py-2.5 w-8">
                        <button
                          onClick={(e) => {
                            const idx = visibleIds.indexOf(item.id)
                            toggleItem(SCOPE, item.id, idx, e.shiftKey, visibleIds)
                          }}
                          className="p-0.5"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          {isSelected(SCOPE, item.id) ? (
                            <CheckSquare size={14} style={{ color: 'var(--accent)' }} />
                          ) : (
                            <Square size={14} />
                          )}
                        </button>
                      </td>
                      <td className="px-3 py-2.5" title={item.file_path}>
                        <div className="flex items-center gap-1.5">
                          <span
                            className="truncate max-w-xs text-sm"
                            style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                          >
                            {item.title || truncatePath(item.file_path)}
                          </span>
                          {item.target_language && (
                            <span
                              className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase"
                              style={{
                                backgroundColor: 'var(--accent-bg)',
                                color: 'var(--accent)',
                                fontFamily: 'var(--font-mono)',
                              }}
                            >
                              {item.target_language}
                            </span>
                          )}
                          {item.instance_name && (
                            <span
                              className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium"
                              style={{
                                backgroundColor: 'var(--bg-surface)',
                                color: 'var(--text-secondary)',
                                border: '1px solid var(--border)',
                              }}
                            >
                              {item.instance_name}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="text-xs" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                          {item.season_episode || (item.item_type === 'movie' ? t('wanted.movie') : '\u2014')}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-1.5">
                          <StatusBadge status={item.status} />
                          <SubtitleTypeBadge subtitleType={item.subtitle_type} />
                        </div>
                      </td>
                      <td className="px-3 py-2.5 hidden sm:table-cell">
                        <div className="flex items-center gap-1.5">
                          <span
                            className="text-xs uppercase"
                            style={{
                              fontFamily: 'var(--font-mono)',
                              color: item.existing_sub === 'srt' ? 'var(--warning)' : 'var(--text-muted)',
                            }}
                          >
                            {item.existing_sub || 'none'}
                          </span>
                          {item.upgrade_candidate === 1 && (
                            <span
                              className="text-[9px] px-1 py-0.5 rounded font-bold uppercase"
                              style={{
                                backgroundColor: 'rgba(16,185,129,0.1)',
                                color: 'var(--success)',
                              }}
                            >
                              SRT&rarr;ASS
                            </span>
                          )}
                        </div>
                      </td>
                      <td
                        className="px-3 py-2.5 text-xs tabular-nums hidden md:table-cell"
                        style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                      >
                        {item.search_count}
                      </td>
                      <td
                        className="px-3 py-2.5 text-xs tabular-nums hidden lg:table-cell"
                        style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                      >
                        {item.last_search_at ? formatRelativeTime(item.last_search_at) : t('wanted.never')}
                      </td>
                      <td
                        className="px-3 py-2.5 text-xs tabular-nums hidden lg:table-cell"
                        style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                      >
                        {item.added_at ? formatRelativeTime(item.added_at) : ''}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <div className="flex items-center justify-end gap-1">
                          {(item.existing_sub === 'ass' || item.existing_sub === 'srt') && item.file_path && item.target_language && (
                            <button
                              onClick={() => setPreviewFilePath(deriveSubtitlePath(item.file_path, item.target_language, item.existing_sub))}
                              className="p-1 rounded transition-colors duration-150"
                              title="Preview subtitle"
                              style={{ color: 'var(--text-muted)' }}
                              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                            >
                              <Eye size={14} />
                            </button>
                          )}
                          <button
                            onClick={() => handleSearch(item.id)}
                            disabled={searchItem.isPending && expandedItem === item.id}
                            className="p-1 rounded transition-colors duration-150"
                            title={t('wanted.search_providers')}
                            style={{ color: expandedItem === item.id ? 'var(--accent)' : 'var(--text-muted)' }}
                            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                            onMouseLeave={(e) => {
                              if (expandedItem !== item.id) e.currentTarget.style.color = 'var(--text-muted)'
                            }}
                          >
                            {searchItem.isPending && expandedItem === item.id
                              ? <Loader2 size={14} className="animate-spin" />
                              : expandedItem === item.id ? <ChevronUp size={14} /> : <Search size={14} />
                            }
                          </button>
                          {(item.existing_sub === 'embedded_ass' || item.existing_sub === 'embedded_srt') && (
                            <button
                              onClick={() => handleExtract(item.id, item.target_language)}
                              disabled={extractItem.isPending}
                              className="p-1 rounded transition-colors duration-150"
                              title={t('wanted.extract_embedded')}
                              style={{ color: 'var(--text-muted)' }}
                              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                            >
                              {extractItem.isPending ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                            </button>
                          )}
                          <button
                            onClick={() => setInteractiveItem({ id: item.id, title: item.title })}
                            className="p-1 rounded transition-colors duration-150"
                            title="Interaktive Suche"
                            style={{ color: 'var(--text-muted)' }}
                            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                            onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                          >
                            <ScanSearch size={14} />
                          </button>
                          <button
                            onClick={() => handleProcess(item.id)}
                            disabled={processItem.isPending || item.status === 'searching'}
                            className="p-1 rounded transition-colors duration-150"
                            title={t('wanted.download_translate')}
                            style={{ color: 'var(--text-muted)' }}
                            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--success)')}
                            onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                          >
                            <Play size={14} />
                          </button>
                          <button
                            onClick={() => retranslateItem.mutate(item.id)}
                            disabled={retranslateItem.isPending}
                            className="p-1 rounded transition-colors duration-150"
                            title={t('wanted.re_translate')}
                            style={{ color: 'var(--text-muted)' }}
                            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--warning)')}
                            onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                          >
                            <RefreshCw size={14} />
                          </button>
                          <button
                            onClick={() => updateStatus.mutate({
                              itemId: item.id,
                              status: item.status === 'ignored' ? 'wanted' : 'ignored',
                            })}
                            className="p-1 rounded transition-colors duration-150"
                            title={item.status === 'ignored' ? t('wanted.un_ignore_action') : t('wanted.ignore_action')}
                            style={{ color: 'var(--text-muted)' }}
                            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                            onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                          >
                            {item.status === 'ignored' ? <Eye size={14} /> : <EyeOff size={14} />}
                          </button>
                        </div>
                      </td>
                    </tr>
                    {/* Expandable search results */}
                    {expandedItem === item.id && (
                      <SearchResultsRow
                        results={searchResults[item.id] ?? null}
                        isLoading={searchItem.isPending}
                        t={t}
                        onBlacklist={(providerName, subtitleId, language) => {
                          addBlacklist.mutate({
                            provider_name: providerName,
                            subtitle_id: subtitleId,
                            language,
                            title: item.title,
                            file_path: item.file_path,
                            reason: 'Blacklisted from wanted search',
                          })
                        }}
                      />
                    )}
                  </Fragment>
                ))
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

        {/* Pagination */}
        {wanted && wanted.total_pages > 1 && (
          <div
            className="flex items-center justify-between px-4 py-2.5"
            style={{ borderTop: '1px solid var(--border)' }}
          >
            <span className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Page {wanted.page} of {wanted.total_pages} ({wanted.total} total)
            </span>
            <div className="flex gap-1.5">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 rounded-md transition-all duration-150"
                style={{
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-primary)',
                  color: 'var(--text-secondary)',
                }}
                onMouseEnter={(e) => {
                  if (!e.currentTarget.disabled) e.currentTarget.style.borderColor = 'var(--accent-dim)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                }}
              >
                <ChevronLeft size={14} />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(wanted.total_pages, p + 1))}
                disabled={page >= wanted.total_pages}
                className="p-1.5 rounded-md transition-all duration-150"
                style={{
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-primary)',
                  color: 'var(--text-secondary)',
                }}
                onMouseEnter={(e) => {
                  if (!e.currentTarget.disabled) e.currentTarget.style.borderColor = 'var(--accent-dim)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                }}
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Floating BatchActionBar */}
      <BatchActionBar scope={SCOPE} actions={['ignore', 'unignore', 'blacklist', 'export']} />

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
    </div>
  )
}
