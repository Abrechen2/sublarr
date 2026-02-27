import { useState, useMemo, useCallback, memo } from 'react'
import { useTranslation } from 'react-i18next'
import { useHistory, useHistoryStats, useAddToBlacklist } from '@/hooks/useApi'
import { formatRelativeTime, truncatePath } from '@/lib/utils'
import {
  Clock, Download, ChevronLeft, ChevronRight, Ban, Eye, GitCompare,
  CheckSquare, Square, MinusSquare,
} from 'lucide-react'
import SubtitleEditorModal from '@/components/editor/SubtitleEditorModal'
import { FilterBar } from '@/components/filters/FilterBar'
import type { FilterDef, ActiveFilter } from '@/components/filters/FilterBar'
import { BatchActionBar } from '@/components/batch/BatchActionBar'
import { useSelectionStore } from '@/stores/selectionStore'
import type { FilterCondition } from '@/lib/types'

const PROVIDER_FILTERS = ['all', 'animetosho', 'jimaku', 'opensubtitles', 'subdl'] as const

const PROVIDER_LABELS: Record<string, string> = {
  animetosho: 'AnimeTosho',
  jimaku: 'Jimaku',
  opensubtitles: 'OpenSubtitles',
  subdl: 'SubDL',
}

const SCOPE = 'history' as const

type HistoryEntry = {
  id: number
  file_path: string
  provider_name: string
  language: string
  format: string
  score: number
  downloaded_at: string | null
  subtitle_id?: string
}

const HistoryTableRow = memo(function HistoryTableRow({
  entry,
  selected,
  index,
  visibleIds: _visibleIds,
  onToggle,
  onPreview,
  onDiff,
  onBlacklist,
  isBlacklistPending,
  t,
}: {
  entry: HistoryEntry
  selected: boolean
  index: number
  visibleIds: number[]
  onToggle: (itemId: number, idx: number, shiftKey: boolean) => void
  onPreview: (path: string) => void
  onDiff: (path: string) => void
  onBlacklist: (entry: HistoryEntry) => void
  isBlacklistPending: boolean
  t: (key: string) => string
}) {
  return (
    <tr
      className="transition-colors duration-100"
      style={{ borderBottom: '1px solid var(--border)' }}
      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)')}
      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
    >
      <td className="px-3 py-2.5 w-8">
        <button
          onClick={(e) => onToggle(entry.id, index, e.shiftKey)}
          className="p-0.5"
          style={{ color: 'var(--text-muted)' }}
        >
          {selected ? (
            <CheckSquare size={14} style={{ color: 'var(--accent)' }} />
          ) : (
            <Square size={14} />
          )}
        </button>
      </td>
      <td className="px-4 py-2.5" title={entry.file_path}>
        <span className="truncate max-w-xs text-sm block" style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
          {truncatePath(entry.file_path)}
        </span>
      </td>
      <td className="px-3 py-2.5">
        <span className="text-xs font-medium capitalize" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
          {entry.provider_name}
        </span>
      </td>
      <td className="px-3 py-2.5">
        <span className="text-xs uppercase" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
          {entry.language}
        </span>
      </td>
      <td className="px-3 py-2.5">
        <span
          className="text-[10px] px-1.5 py-0.5 rounded uppercase font-bold"
          style={{
            backgroundColor: entry.format === 'ass' ? 'var(--success)18' : 'var(--bg-primary)',
            color: entry.format === 'ass' ? 'var(--success)' : 'var(--text-secondary)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {entry.format || '?'}
        </span>
      </td>
      <td className="px-3 py-2.5 hidden sm:table-cell">
        <span
          className="text-xs tabular-nums"
          style={{
            fontFamily: 'var(--font-mono)',
            color: entry.score >= 300 ? 'var(--success)' : entry.score >= 200 ? 'var(--warning)' : 'var(--text-muted)',
          }}
        >
          {entry.score}
        </span>
      </td>
      <td
        className="px-3 py-2.5 text-xs tabular-nums hidden md:table-cell"
        style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
      >
        {entry.downloaded_at ? formatRelativeTime(entry.downloaded_at) : ''}
      </td>
      <td className="px-4 py-2.5 text-right">
        <div className="flex items-center justify-end gap-1">
          {entry.format && entry.language && entry.file_path && (
            <>
              <button
                onClick={() => {
                  const lastDot = entry.file_path.lastIndexOf('.')
                  const base = lastDot > 0 ? entry.file_path.substring(0, lastDot) : entry.file_path
                  onPreview(`${base}.${entry.language}.${entry.format}`)
                }}
                className="p-1 rounded transition-colors duration-150"
                title="Preview subtitle"
                style={{ color: 'var(--text-muted)' }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
              >
                <Eye size={14} />
              </button>
              <button
                onClick={() => {
                  const lastDot = entry.file_path.lastIndexOf('.')
                  const base = lastDot > 0 ? entry.file_path.substring(0, lastDot) : entry.file_path
                  onDiff(`${base}.${entry.language}.${entry.format}`)
                }}
                className="p-1 rounded transition-colors duration-150"
                title="View diff with backup"
                style={{ color: 'var(--text-muted)' }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
              >
                <GitCompare size={14} />
              </button>
            </>
          )}
          <button
            onClick={() => onBlacklist(entry)}
            disabled={isBlacklistPending}
            className="p-1 rounded transition-colors duration-150"
            title={t('history.add_to_blacklist')}
            style={{ color: 'var(--text-muted)' }}
            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--error)')}
            onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
          >
            <Ban size={14} />
          </button>
        </div>
      </td>
    </tr>
  )
})

const HISTORY_FILTERS: FilterDef[] = [
  { key: 'provider', label: 'Provider', type: 'select' as const, options: [
    { value: 'animetosho', label: 'AnimeTosho' },
    { value: 'jimaku',     label: 'Jimaku' },
    { value: 'opensubtitles', label: 'OpenSubtitles' },
    { value: 'subdl',      label: 'SubDL' },
  ]},
  { key: 'format', label: 'Format', type: 'select' as const, options: [
    { value: 'ass', label: 'ASS' },
    { value: 'srt', label: 'SRT' },
  ]},
  { key: 'language', label: 'Language', type: 'text' as const },
  { key: 'file_path', label: 'File Path', type: 'text' as const },
]

function SummaryCard({ icon: Icon, label, value, color }: {
  icon: typeof Clock
  label: string
  value: number | string
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

export function HistoryPage() {
  const { t } = useTranslation('activity')
  const [page, setPage] = useState(1)
  const [providerFilter, setProviderFilter] = useState<string | undefined>()
  const [languageFilter, setLanguageFilter] = useState<string | undefined>()
  const [editorFilePath, setEditorFilePath] = useState<string | null>(null)
  const [editorMode, setEditorMode] = useState<'preview' | 'edit' | 'diff'>('preview')
  const [activeFilters, setActiveFilters] = useState<ActiveFilter[]>([])

  // Zustand selection store: subscribe only to this scope to avoid re-renders from other pages
  const scopeSelections = useSelectionStore((s) => s.selections[SCOPE])
  const toggleItem = useSelectionStore((s) => s.toggleItem)
  const selectAll = useSelectionStore((s) => s.selectAll)
  const clearSelection = useSelectionStore((s) => s.clearSelection)
  const isSelected = useCallback((id: number) => (scopeSelections ?? new Set()).has(id), [scopeSelections])

  const { data: history, isLoading } = useHistory(page, 50, providerFilter, languageFilter)
  const { data: stats } = useHistoryStats()
  const addBlacklist = useAddToBlacklist()

  const topProvider = stats?.by_provider
    ? Object.entries(stats.by_provider).sort((a, b) => b[1] - a[1])[0]?.[0] ?? '-'
    : '-'

  // Client-side filtering by format and file_path from FilterBar
  const filteredData = useMemo(() => {
    let data = history?.data
    if (!data) return data
    const formatFilter = activeFilters.find(f => f.key === 'format')?.value
    if (formatFilter) {
      data = data.filter((entry) => entry.format === formatFilter)
    }
    const pathFilter = activeFilters.find(f => f.key === 'file_path')?.value
    if (pathFilter) {
      const q = pathFilter.toLowerCase()
      data = data.filter((entry) => entry.file_path.toLowerCase().includes(q))
    }
    return data
  }, [history?.data, activeFilters])

  // Visible IDs for selection
  const visibleIds = useMemo(() => filteredData?.map((d) => d.id) ?? [], [filteredData])
  const allSelected = visibleIds.length > 0 && visibleIds.every((id) => isSelected(id))
  const someSelected = visibleIds.some((id) => isSelected(id))

  const toggleSelectAll = useCallback(() => {
    if (allSelected) {
      clearSelection(SCOPE)
    } else {
      selectAll(SCOPE, visibleIds)
    }
  }, [allSelected, visibleIds, clearSelection, selectAll])

  const onToggleSelection = useCallback((itemId: number, idx: number, shiftKey: boolean) => {
    toggleItem(SCOPE, itemId, idx, shiftKey, visibleIds)
  }, [toggleItem, visibleIds])

  const onPreviewPath = useCallback((path: string) => {
    setEditorFilePath(path)
    setEditorMode('preview')
  }, [])

  const onDiffPath = useCallback((path: string) => {
    setEditorFilePath(path)
    setEditorMode('diff')
  }, [])

  const onBlacklistEntry = useCallback((entry: HistoryEntry) => {
    addBlacklist.mutate({
      provider_name: entry.provider_name,
      subtitle_id: entry.subtitle_id ?? '',
      language: entry.language,
      file_path: entry.file_path,
      reason: t('history.blacklisted_from_history'),
    })
  }, [addBlacklist, t])

  const handleFiltersChange = useCallback((filters: ActiveFilter[]) => {
    setActiveFilters(filters)
    setPage(1)
    // Sync provider and language filters to API query params
    const providerVal = filters.find(f => f.key === 'provider')?.value
    setProviderFilter(providerVal)
    const langVal = filters.find(f => f.key === 'language')?.value
    setLanguageFilter(langVal)
  }, [])

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1>{t('history.title')}</h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
          {t('history.subtitle')}
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <SummaryCard icon={Download} label={t('history.total_downloads')} value={stats?.total_downloads ?? 0} color="var(--accent)" />
        <SummaryCard icon={Clock} label={t('history.last_24h')} value={stats?.last_24h ?? 0} color="var(--success)" />
        <SummaryCard icon={Clock} label={t('history.last_7d')} value={stats?.last_7d ?? 0} color="var(--warning)" />
        <SummaryCard icon={Download} label={t('history.top_provider')} value={topProvider} color="var(--text-secondary)" />
      </div>

      {/* Provider Filter Buttons */}
      <div className="flex flex-wrap items-center gap-1.5">
        {PROVIDER_FILTERS.map((p) => {
          const isActive = (p === 'all' && !providerFilter) || providerFilter === p
          return (
            <button
              key={p}
              onClick={() => {
                setProviderFilter(p === 'all' ? undefined : p)
                setPage(1)
                // Sync to FilterBar activeFilters
                if (p === 'all') {
                  setActiveFilters(prev => prev.filter(f => f.key !== 'provider'))
                } else {
                  setActiveFilters(prev => {
                    const without = prev.filter(f => f.key !== 'provider')
                    return [...without, { key: 'provider', op: 'eq' as const, value: p, label: 'Provider' }]
                  })
                }
              }}
              className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
              style={{
                backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--bg-surface)',
                color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                border: `1px solid ${isActive ? 'var(--accent-dim)' : 'var(--border)'}`,
              }}
            >
              {p === 'all' ? t('history.all_providers') : (PROVIDER_LABELS[p] ?? p)}
            </button>
          )
        })}
      </div>

      {/* FilterBar */}
      <FilterBar
        scope={SCOPE}
        filters={HISTORY_FILTERS}
        activeFilters={activeFilters}
        onFiltersChange={handleFiltersChange}
        onPresetLoad={(conditions) => {
          if (conditions.logic === 'AND') {
            const filters = conditions.conditions
              .filter((c): c is FilterCondition => 'field' in c)
              .map((c) => {
                const def = HISTORY_FILTERS.find(f => f.key === c.field)
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
          <table className="w-full min-w-[600px]">
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
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('history.table.file')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('history.table.provider')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('history.table.lang')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('history.table.format')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>{t('history.table.score')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden md:table-cell" style={{ color: 'var(--text-muted)' }}>{t('history.table.date')}</th>
                <th className="text-right text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('history.table.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="px-3 py-3"><div className="skeleton h-4 w-4 rounded" /></td>
                    <td className="px-4 py-3"><div className="skeleton h-4 w-48 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-4 w-20 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-4 w-8 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-4 w-10 rounded" /></td>
                    <td className="px-3 py-3 hidden sm:table-cell"><div className="skeleton h-4 w-8 rounded" /></td>
                    <td className="px-3 py-3 hidden md:table-cell"><div className="skeleton h-4 w-14 rounded" /></td>
                    <td className="px-4 py-3"><div className="skeleton h-4 w-6 rounded ml-auto" /></td>
                  </tr>
                ))
              ) : filteredData?.length ? (
                filteredData.map((entry, index) => (
                  <HistoryTableRow
                    key={entry.id}
                    entry={entry}
                    selected={isSelected(entry.id)}
                    index={index}
                    visibleIds={visibleIds}
                    onToggle={onToggleSelection}
                    onPreview={onPreviewPath}
                    onDiff={onDiffPath}
                    onBlacklist={onBlacklistEntry}
                    isBlacklistPending={addBlacklist.isPending}
                    t={t}
                  />
                ))
              ) : (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
                    {t('history.no_history')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {history && history.total_pages > 1 && (
          <div
            className="flex items-center justify-between px-4 py-2.5"
            style={{ borderTop: '1px solid var(--border)' }}
          >
            <span className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              {t('page_info', { page: history.page, totalPages: history.total_pages, total: history.total })}
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
              >
                <ChevronLeft size={14} />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(history.total_pages, p + 1))}
                disabled={page >= history.total_pages}
                className="p-1.5 rounded-md transition-all duration-150"
                style={{
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-primary)',
                  color: 'var(--text-secondary)',
                }}
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Floating BatchActionBar */}
      <BatchActionBar scope={SCOPE} actions={['export']} />

      {/* Subtitle Editor Modal */}
      {editorFilePath && (
        <SubtitleEditorModal
          filePath={editorFilePath}
          initialMode={editorMode}
          onClose={() => setEditorFilePath(null)}
        />
      )}
    </div>
  )
}
