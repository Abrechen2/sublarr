import { useRef, useEffect, memo } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'
import type { SeriesInfo, MovieInfo, LanguageProfile } from '@/lib/types'
import { ProgressBar, MissingBadge } from './LibraryShared'

type Tab = 'series' | 'movies'
type SortKey = 'title' | 'missing' | 'episodes'
type SortDir = 'asc' | 'desc'

function SortIcon({
  sortKey,
  currentSort,
  currentDir,
}: {
  sortKey: SortKey
  currentSort: SortKey
  currentDir: SortDir
}) {
  if (currentSort !== sortKey)
    return <ArrowUpDown size={11} style={{ color: 'var(--text-muted)', opacity: 0.5 }} />
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
  selected,
  onToggle,
}: {
  item: SeriesInfo | MovieInfo
  isSeries: boolean
  profiles: LanguageProfile[]
  onRowClick: (id: number) => void
  onProfileChange: (seriesId: number, profileId: number) => void
  t: (key: string, opts?: Record<string, unknown>) => string
  selected: boolean
  onToggle: () => void
}) {
  return (
    <tr
      data-testid="library-row"
      className="transition-colors duration-100 cursor-pointer"
      style={{ borderTop: '1px solid var(--border)' }}
      onClick={() => onRowClick(item.id)}
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)' }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '' }}
    >
      {isSeries && (
        <td className="w-10 pl-3" onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="rounded"
            style={{ accentColor: 'var(--accent)' }}
          />
        </td>
      )}
      <td className="px-4 py-2.5 max-w-xs">
        <span
          className="text-sm font-medium hover:underline block truncate"
          title={item.title}
          style={{ color: 'var(--accent)' }}
        >
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
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
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

export function VirtualLibraryTable({
  items,
  type,
  profiles,
  onRowClick,
  onProfileChange,
  sortKey,
  sortDir,
  onSort,
  t,
  selectedSeries,
  onToggleSeries,
  onSelectAll,
  onClearSelection,
}: {
  items: (SeriesInfo | MovieInfo)[]
  type: Tab
  profiles: LanguageProfile[]
  onRowClick: (id: number) => void
  onProfileChange: (seriesId: number, profileId: number) => void
  sortKey: SortKey
  sortDir: SortDir
  onSort: (key: SortKey) => void
  t: (key: string, opts?: Record<string, unknown>) => string
  selectedSeries: Set<number>
  onToggleSeries: (id: number) => void
  onSelectAll: () => void
  onClearSelection: () => void
}) {
  const isSeries = type === 'series'
  const allSelected = isSeries && items.length > 0 && selectedSeries.size === items.length
  // series: checkbox + title + missing + profile + episodes = 5 cols
  // movies: title + profile + status = 3 cols
  // Update this when adding/removing columns to prevent silent spacer-row layout bugs
  const colSpan = isSeries ? 5 : 3

  const parentRef = useRef<HTMLDivElement>(null)
  const rowVirtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 40,
    overscan: 8,
  })
  // Reset scroll to top when items array changes (filter/sort applied)
  useEffect(() => {
    parentRef.current?.scrollTo({ top: 0 })
  }, [items])

  const virtualItems = rowVirtualizer.getVirtualItems()
  const paddingTop = virtualItems.length > 0 ? virtualItems[0].start : 0
  const paddingBottom =
    virtualItems.length > 0
      ? rowVirtualizer.getTotalSize() - virtualItems[virtualItems.length - 1].end
      : 0

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ border: '1px solid var(--border)' }}
    >
      <div ref={parentRef} style={{ height: 'calc(100vh - 280px)', overflowY: 'auto' }}>
        <table className="w-full">
          <thead
            style={{
              position: 'sticky',
              top: 0,
              zIndex: 1,
              backgroundColor: 'var(--bg-elevated)',
            }}
          >
            <tr>
              {isSeries && (
                <th scope="col" className="w-10 pl-3">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={() => (allSelected ? onClearSelection() : onSelectAll())}
                    className="rounded"
                    title="Select all visible"
                    style={{ accentColor: 'var(--accent)' }}
                  />
                </th>
              )}
              <th
                scope="col"
                aria-sort={
                  sortKey === 'title'
                    ? sortDir === 'asc'
                      ? 'ascending'
                      : 'descending'
                    : 'none'
                }
                className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5 cursor-pointer select-none"
                style={{ color: 'var(--text-secondary)' }}
                onClick={() => onSort('title')}
              >
                <span className="inline-flex items-center gap-1.5">
                  {t('table.name')}{' '}
                  <SortIcon sortKey="title" currentSort={sortKey} currentDir={sortDir} />
                </span>
              </th>
              {isSeries && (
                <th
                  scope="col"
                  aria-sort={
                    sortKey === 'missing'
                      ? sortDir === 'asc'
                        ? 'ascending'
                        : 'descending'
                      : 'none'
                  }
                  className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5 w-20 cursor-pointer select-none"
                  style={{ color: 'var(--text-secondary)' }}
                  onClick={() => onSort('missing')}
                >
                  <span className="inline-flex items-center gap-1.5">
                    {t('table.missing')}{' '}
                    <SortIcon sortKey="missing" currentSort={sortKey} currentDir={sortDir} />
                  </span>
                </th>
              )}
              <th
                scope="col"
                className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5 w-40"
                style={{ color: 'var(--text-secondary)' }}
              >
                {t('table.profile')}
              </th>
              <th
                scope="col"
                aria-sort={
                  sortKey === 'episodes'
                    ? sortDir === 'asc'
                      ? 'ascending'
                      : 'descending'
                    : 'none'
                }
                className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5 w-44 cursor-pointer select-none"
                style={{ color: 'var(--text-secondary)' }}
                onClick={() => onSort('episodes')}
              >
                <span className="inline-flex items-center gap-1.5">
                  {isSeries ? t('table.episodes') : t('table.status')}{' '}
                  <SortIcon sortKey="episodes" currentSort={sortKey} currentDir={sortDir} />
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {paddingTop > 0 && (
              <tr aria-hidden="true">
                <td colSpan={colSpan} style={{ height: paddingTop, padding: 0 }} />
              </tr>
            )}
            {virtualItems.map((virtualRow) => (
              <LibraryTableRow
                key={virtualRow.key}
                item={items[virtualRow.index]}
                isSeries={isSeries}
                profiles={profiles}
                onRowClick={onRowClick}
                onProfileChange={onProfileChange}
                t={t}
                selected={selectedSeries.has(items[virtualRow.index].id)}
                onToggle={() => onToggleSeries(items[virtualRow.index].id)}
              />
            ))}
            {paddingBottom > 0 && (
              <tr aria-hidden="true">
                <td colSpan={colSpan} style={{ height: paddingBottom, padding: 0 }} />
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
