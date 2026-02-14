import { useState, useMemo, useCallback, Fragment } from 'react'
import {
  useWantedItems, useWantedSummary, useRefreshWanted, useUpdateWantedStatus,
  useSearchWantedItem, useProcessWantedItem, useStartWantedBatch, useWantedBatchStatus,
  useRetranslateSingle, useAddToBlacklist, useExtractEmbeddedSub,
} from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { formatRelativeTime, truncatePath } from '@/lib/utils'
import { toast } from '@/components/shared/Toast'
import type { WantedSearchResponse } from '@/lib/types'
import {
  RefreshCw, ChevronLeft, ChevronRight, Search, Film, Tv,
  ArrowUpCircle, EyeOff, Eye, Play, Loader2, ChevronUp, Ban,
  CheckSquare, Square, MinusSquare, Download,
} from 'lucide-react'

const STATUS_FILTERS = ['all', 'wanted', 'failed', 'ignored'] as const
const TYPE_FILTERS = ['all', 'episode', 'movie'] as const

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

function SearchResultsRow({ results, isLoading, onBlacklist }: {
  results: WantedSearchResponse | null
  isLoading: boolean
  onBlacklist: (providerName: string, subtitleId: string, language: string) => void
}) {
  if (isLoading) {
    return (
      <tr style={{ backgroundColor: 'var(--bg-primary)' }}>
        <td colSpan={9} className="px-6 py-4">
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
            <Loader2 size={14} className="animate-spin" />
            Searching providers...
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
          No results found from any provider.
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
                      title="Blacklist this subtitle"
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
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [typeFilter, setTypeFilter] = useState<string | undefined>()
  const [upgradeFilter, setUpgradeFilter] = useState(false)
  const [languageFilter, setLanguageFilter] = useState<string | undefined>()
  const [expandedItem, setExpandedItem] = useState<number | null>(null)
  const [searchResults, setSearchResults] = useState<Record<number, WantedSearchResponse>>({})
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  const { data: summary } = useWantedSummary()
  const { data: wanted, isLoading } = useWantedItems(page, 50, typeFilter, statusFilter)
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

  // Extract unique languages from data
  const availableLanguages = useMemo(() => {
    if (!wanted?.data) return []
    const langs = new Set<string>()
    for (const item of wanted.data) {
      if (item.target_language) langs.add(item.target_language)
    }
    return Array.from(langs).sort()
  }, [wanted?.data])

  // Client-side filters
  const filteredData = useMemo(() => {
    let data = wanted?.data
    if (!data) return data
    if (upgradeFilter) {
      data = data.filter((item) => item.upgrade_candidate === 1)
    }
    if (languageFilter) {
      data = data.filter((item) => item.target_language === languageFilter)
    }
    return data
  }, [wanted?.data, upgradeFilter, languageFilter])

  // Bulk selection helpers
  const visibleIds = useMemo(() => filteredData?.map((d) => d.id) ?? [], [filteredData])
  const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id))
  const someSelected = visibleIds.some((id) => selectedIds.has(id))

  const toggleSelectAll = useCallback(() => {
    if (allSelected) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(visibleIds))
    }
  }, [allSelected, visibleIds])

  const toggleSelect = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }, [])

  const [bulkRunning, setBulkRunning] = useState(false)

  const handleBulkAction = useCallback(async (action: 'ignore' | 'unignore' | 'search') => {
    const ids = Array.from(selectedIds)
    if (ids.length === 0) return
    setBulkRunning(true)
    try {
      for (const id of ids) {
        if (action === 'ignore') {
          await updateStatus.mutateAsync({ itemId: id, status: 'ignored' })
        } else if (action === 'unignore') {
          await updateStatus.mutateAsync({ itemId: id, status: 'wanted' })
        } else if (action === 'search') {
          await searchItem.mutateAsync(id)
        }
      }
      toast(`${action === 'search' ? 'Searched' : action === 'ignore' ? 'Ignored' : 'Un-ignored'} ${ids.length} items`)
      setSelectedIds(new Set())
    } catch {
      toast('Bulk action failed', 'error')
    } finally {
      setBulkRunning(false)
    }
  }, [selectedIds, updateStatus, searchItem])

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
    processItem.mutate(itemId)
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
              Processing: {batchStatus.current_item || 'Starting...'}
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
            <span>Found: {batchStatus.found}</span>
            <span>Failed: {batchStatus.failed}</span>
            <span>Skipped: {batchStatus.skipped}</span>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1>Wanted</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
            {summary?.total ?? 0} items missing subtitles
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
            {batchStatus?.running ? 'Searching...' : 'Search All'}
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
            {summary?.scan_running ? 'Scanning...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <SummaryCard icon={Search} label="Total Wanted" value={totalWanted} color="var(--warning)" />
        <SummaryCard icon={Tv} label="Episodes" value={totalEpisodes} color="var(--accent)" />
        <SummaryCard icon={Film} label="Movies" value={totalMovies} color="var(--text-secondary)" />
        <SummaryCard icon={ArrowUpCircle} label="SRT Upgradeable" value={upgradeable} color="var(--success)" />
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

      {/* Bulk Action Bar */}
      {selectedIds.size > 0 && (
        <div
          className="rounded-lg p-3 flex items-center justify-between flex-wrap gap-2"
          style={{ backgroundColor: 'var(--accent-bg)', border: '1px solid var(--accent-dim)' }}
        >
          <span className="text-sm font-medium" style={{ color: 'var(--accent)' }}>
            {selectedIds.size} selected
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleBulkAction('ignore')}
              disabled={bulkRunning}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150"
              style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            >
              <EyeOff size={12} />
              Ignore
            </button>
            <button
              onClick={() => handleBulkAction('unignore')}
              disabled={bulkRunning}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150"
              style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            >
              <Eye size={12} />
              Un-ignore
            </button>
            <button
              onClick={() => handleBulkAction('search')}
              disabled={bulkRunning}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150"
              style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            >
              {bulkRunning ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />}
              Search
            </button>
            <button
              onClick={() => setSelectedIds(new Set())}
              className="px-2 py-1.5 rounded text-xs"
              style={{ color: 'var(--text-muted)' }}
            >
              Clear
            </button>
          </div>
        </div>
      )}

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
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>Title</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>S/E</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>Status</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>Existing</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden md:table-cell" style={{ color: 'var(--text-muted)' }}>Searches</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden lg:table-cell" style={{ color: 'var(--text-muted)' }}>Last Search</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden lg:table-cell" style={{ color: 'var(--text-muted)' }}>Added</th>
                <th className="text-right text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>Actions</th>
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
                          onClick={() => toggleSelect(item.id)}
                          className="p-0.5"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          {selectedIds.has(item.id) ? (
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
                          {item.season_episode || (item.item_type === 'movie' ? 'Movie' : '\u2014')}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <StatusBadge status={item.status} />
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
                        {item.last_search_at ? formatRelativeTime(item.last_search_at) : 'Never'}
                      </td>
                      <td
                        className="px-3 py-2.5 text-xs tabular-nums hidden lg:table-cell"
                        style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                      >
                        {item.added_at ? formatRelativeTime(item.added_at) : ''}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleSearch(item.id)}
                            disabled={searchItem.isPending && expandedItem === item.id}
                            className="p-1 rounded transition-colors duration-150"
                            title="Search providers"
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
                              title="Extract embedded subtitle"
                              style={{ color: 'var(--text-muted)' }}
                              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                            >
                              {extractItem.isPending ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                            </button>
                          )}
                          <button
                            onClick={() => handleProcess(item.id)}
                            disabled={processItem.isPending || item.status === 'searching'}
                            className="p-1 rounded transition-colors duration-150"
                            title="Download + translate"
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
                            title="Re-translate"
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
                            title={item.status === 'ignored' ? 'Un-ignore' : 'Ignore'}
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
                    {statusFilter || typeFilter || languageFilter ? 'No items match the current filters' : 'No wanted items — run a scan to detect missing subtitles'}
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
    </div>
  )
}
