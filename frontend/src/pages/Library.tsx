import { useState, useMemo, useCallback, memo } from 'react'
import { useTranslation } from 'react-i18next'
import { useLibrary, useLanguageProfiles, useAssignProfile } from '@/hooks/useApi'
import { Tv, Film, Loader2, Settings, ChevronLeft, ChevronRight, Search, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { SeriesInfo, MovieInfo, LanguageProfile } from '@/lib/types'

type Tab = 'series' | 'movies'
type SortKey = 'title' | 'missing' | 'episodes'
type SortDir = 'asc' | 'desc'
const PAGE_SIZE = 25

function ProgressBar({ current, total }: { current: number; total: number }) {
  const pct = total > 0 ? (current / total) * 100 : 0
  const isComplete = current === total && total > 0
  const isEmpty = total === 0

  const barColor = isEmpty
    ? 'var(--text-muted)'
    : isComplete
      ? 'var(--success)'
      : 'var(--warning)'

  return (
    <div className="flex items-center gap-2.5">
      <div
        className="flex-1 h-[18px] rounded-sm overflow-hidden relative"
        style={{ backgroundColor: 'var(--bg-primary)', minWidth: 80 }}
      >
        <div
          className="h-full rounded-sm transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: barColor }}
        />
        <span
          className="absolute inset-0 flex items-center justify-center text-[11px] font-medium"
          style={{
            color: pct > 50 ? '#fff' : 'var(--text-secondary)',
            fontFamily: 'var(--font-mono)',
            textShadow: pct > 50 ? '0 1px 2px rgba(0,0,0,0.4)' : 'none',
          }}
        >
          {current}/{total}
        </span>
      </div>
    </div>
  )
}

function MissingBadge({ count }: { count: number }) {
  const color = count > 5 ? 'var(--error)' : count > 0 ? 'var(--warning)' : 'var(--success)'
  const bg = count > 5 ? 'var(--error-bg)' : count > 0 ? 'var(--warning-bg)' : 'var(--success-bg)'
  return (
    <span
      className="inline-flex items-center justify-center min-w-[28px] px-1.5 py-0.5 rounded text-[11px] font-bold tabular-nums"
      style={{ backgroundColor: bg, color, fontFamily: 'var(--font-mono)' }}
    >
      {count}
    </span>
  )
}

function SortIcon({ sortKey, currentSort, currentDir }: { sortKey: SortKey; currentSort: SortKey; currentDir: SortDir }) {
  if (currentSort !== sortKey) return <ArrowUpDown size={11} style={{ color: 'var(--text-muted)', opacity: 0.5 }} />
  return currentDir === 'asc'
    ? <ArrowUp size={11} style={{ color: 'var(--accent)' }} />
    : <ArrowDown size={11} style={{ color: 'var(--accent)' }} />
}

const LibraryTableRow = memo(function LibraryTableRow({
  item,
  isSeries,
  profiles,
  onRowClick,
  onProfileChange,
  t,
}: {
  item: SeriesInfo | MovieInfo
  isSeries: boolean
  profiles: LanguageProfile[]
  onRowClick: (id: number) => void
  onProfileChange: (seriesId: number, profileId: number) => void
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  return (
    <tr
      className="transition-colors duration-100 cursor-pointer"
      style={{ borderTop: '1px solid var(--border)' }}
      onClick={() => onRowClick(item.id)}
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)' }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '' }}
    >
      <td className="px-4 py-2.5">
        <span className="text-sm font-medium hover:underline" style={{ color: 'var(--accent)' }}>
          {item.title}
        </span>
      </td>
      {isSeries && (
        <td className="px-4 py-2.5">
          <MissingBadge count={(item as SeriesInfo).missing_count ?? 0} />
        </td>
      )}
      <td className="px-4 py-2.5" onClick={(e) => e.stopPropagation()}>
        {isSeries && profiles.length > 0 ? (
          <select
            value={(item as SeriesInfo).profile_id ?? 0}
            onChange={(e) => onProfileChange(item.id, Number(e.target.value))}
            className="text-xs px-2 py-1 rounded cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border)',
            }}
          >
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        ) : (
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            {(item as SeriesInfo).profile_name || t('table.default_profile')}
          </span>
        )}
      </td>
      <td className="px-4 py-2.5">
        {isSeries && 'episodes' in item ? (
          <ProgressBar
            current={(item as SeriesInfo).episodes_with_files || 0}
            total={(item as SeriesInfo).episodes}
          />
        ) : (
          <span
            className="text-[10px] px-2 py-0.5 rounded font-medium inline-block"
            style={{
              backgroundColor: (item as MovieInfo).has_file ? 'var(--success-bg)' : 'var(--error-bg)',
              color: (item as MovieInfo).has_file ? 'var(--success)' : 'var(--error)',
            }}
          >
            {(item as MovieInfo).has_file ? t('table.on_disk') : t('table.missing_file')}
          </span>
        )}
      </td>
    </tr>
  )
})

function LibraryTable({ items, type, profiles, onRowClick, onProfileChange, sortKey, sortDir, onSort, t }: {
  items: (SeriesInfo | MovieInfo)[]
  type: Tab
  profiles: LanguageProfile[]
  onRowClick: (id: number) => void
  onProfileChange: (seriesId: number, profileId: number) => void
  sortKey: SortKey
  sortDir: SortDir
  onSort: (key: SortKey) => void
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  const isSeries = type === 'series'

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ border: '1px solid var(--border)' }}
    >
      <table className="w-full">
        <thead>
          <tr style={{ backgroundColor: 'var(--bg-elevated)' }}>
            <th
              className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5 cursor-pointer select-none"
              style={{ color: 'var(--text-secondary)' }}
              onClick={() => onSort('title')}
            >
              <span className="inline-flex items-center gap-1.5">
                {t('table.name')} <SortIcon sortKey="title" currentSort={sortKey} currentDir={sortDir} />
              </span>
            </th>
            {isSeries && (
              <th
                className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5 w-20 cursor-pointer select-none"
                style={{ color: 'var(--text-secondary)' }}
                onClick={() => onSort('missing')}
              >
                <span className="inline-flex items-center gap-1.5">
                  {t('table.missing')} <SortIcon sortKey="missing" currentSort={sortKey} currentDir={sortDir} />
                </span>
              </th>
            )}
            <th
              className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5 w-40"
              style={{ color: 'var(--text-secondary)' }}
            >
              {t('table.profile')}
            </th>
            <th
              className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5 w-44 cursor-pointer select-none"
              style={{ color: 'var(--text-secondary)' }}
              onClick={() => onSort('episodes')}
            >
              <span className="inline-flex items-center gap-1.5">
                {isSeries ? t('table.episodes') : t('table.status')} <SortIcon sortKey="episodes" currentSort={sortKey} currentDir={sortDir} />
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <LibraryTableRow
              key={item.id}
              item={item}
              isSeries={isSeries}
              profiles={profiles}
              onRowClick={onRowClick}
              onProfileChange={onProfileChange}
              t={t}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

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

export function LibraryPage() {
  const { t } = useTranslation('library')
  const { data: library, isLoading } = useLibrary()
  const { data: profiles } = useLanguageProfiles()
  const assignProfile = useAssignProfile()
  const [activeTab, setActiveTab] = useState<Tab>('series')
  const [page, setPage] = useState(1)
  const [searchQuery, setSearchQuery] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('title')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const navigate = useNavigate()

  const handleSort = useCallback((key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir(key === 'missing' ? 'desc' : 'asc')
    }
    setPage(1)
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
  }, [library, activeTab, searchQuery, sortKey, sortDir])

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

  // Pagination
  const totalPages = Math.ceil(processedItems.length / PAGE_SIZE)
  const currentPage = Math.min(page, totalPages || 1)
  const paginatedItems = processedItems.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  // Reset page on tab change
  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab)
    setPage(1)
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
              type="text"
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); setPage(1) }}
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
        </div>
      </div>

      {paginatedItems.length === 0 ? (
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
          <LibraryTable
            items={paginatedItems}
            type={activeTab}
            profiles={profiles || []}
            onRowClick={handleRowClick}
            onProfileChange={handleProfileChange}
            sortKey={sortKey}
            sortDir={sortDir}
            onSort={handleSort}
            t={t}
          />
          {totalPages > 1 && (
            <Pagination
              page={currentPage}
              totalPages={totalPages}
              total={processedItems.length}
              pageSize={PAGE_SIZE}
              onPageChange={setPage}
              t={t}
            />
          )}
        </>
      )}
    </div>
  )
}
