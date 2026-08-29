import { useTranslation } from 'react-i18next'
import { Search, Film, Tv, ArrowUpCircle, ArrowUp, ArrowDown, Ban } from 'lucide-react'
import { FilterBar } from '@/components/filters/FilterBar'
import type { FilterDef, ActiveFilter } from '@/components/filters/FilterBar'
import type { FilterCondition } from '@/lib/types'

const STATUS_FILTERS = ['all', 'wanted', 'extracted', 'failed', 'ignored'] as const
const TYPE_FILTERS = ['all', 'episode', 'movie'] as const
const SUBTITLE_TYPE_FILTERS = ['all', 'full', 'forced'] as const

const STATUS_I18N: Record<string, string> = {
  all: 'wanted.all',
  wanted: 'wanted.wanted_status',
  extracted: 'wanted.extracted_status',
  failed: 'wanted.failed',
  ignored: 'wanted.ignored',
}
const TYPE_I18N: Record<string, string> = {
  all: 'wanted.all_types',
  episode: 'wanted.episodes',
  movie: 'wanted.movie',
}
const SUBTITLE_TYPE_I18N: Record<string, string> = {
  all: 'wanted.all_subs',
  full: 'wanted.subtitle_type_full',
  forced: 'wanted.subtitle_type_forced',
}

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

export interface WantedFilterPanelProps {
  scope: 'wanted'
  wantedFilters: FilterDef[]
  // Summary card values
  totalWanted: number
  totalEpisodes: number
  totalMovies: number
  upgradeable: number
  /** Wanted items the search will never pick up again (#199). */
  exhausted: number
  forcedCount: number
  // Filter state
  statusFilter: string | undefined
  typeFilter: string | undefined
  subtitleTypeFilter: string | undefined
  upgradeFilter: boolean
  languageFilter: string | undefined
  availableLanguages: string[]
  // FilterBar state
  activeFilters: ActiveFilter[]
  sortBy: string
  sortDir: 'asc' | 'desc'
  searchText: string
  // Handlers
  onStatusFilter: (val: string | undefined) => void
  onTypeFilter: (val: string | undefined) => void
  onSubtitleTypeFilter: (val: string | undefined) => void
  onUpgradeFilter: (val: boolean) => void
  onLanguageFilter: (val: string | undefined) => void
  onFiltersChange: (filters: ActiveFilter[]) => void
  onSortBy: (val: string) => void
  onSortDir: (val: 'asc' | 'desc') => void
  onSearchText: (val: string) => void
}

export function WantedFilterPanel({
  scope,
  wantedFilters,
  totalWanted,
  totalEpisodes,
  totalMovies,
  upgradeable,
  exhausted,
  forcedCount,
  statusFilter,
  typeFilter,
  subtitleTypeFilter,
  upgradeFilter,
  languageFilter,
  availableLanguages,
  activeFilters,
  sortBy,
  sortDir,
  searchText,
  onStatusFilter,
  onTypeFilter,
  onSubtitleTypeFilter,
  onUpgradeFilter,
  onLanguageFilter,
  onFiltersChange,
  onSortBy,
  onSortDir,
  onSearchText,
}: WantedFilterPanelProps) {
  const { t } = useTranslation('library')

  const handlePresetLoad = (conditions: { logic: string; conditions: unknown[] }) => {
    if (conditions.logic === 'AND') {
      const filters = (conditions.conditions as FilterCondition[])
        .filter((c): c is FilterCondition => 'field' in c)
        .map((c) => {
          const def = wantedFilters.find(f => f.key === c.field)
          return { key: c.field, op: c.op, value: String(c.value), label: def?.label ?? c.field }
        })
      onFiltersChange(filters)
    }
  }

  return (
    <>
      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <SummaryCard icon={Search} label={t('wanted.total_wanted')} value={totalWanted} color="var(--warning)" />
        <SummaryCard icon={Tv} label={t('wanted.episodes')} value={totalEpisodes} color="var(--accent)" />
        <SummaryCard icon={Film} label={t('wanted.movies')} value={totalMovies} color="var(--text-secondary)" />
        <SummaryCard icon={ArrowUpCircle} label={t('wanted.srt_upgradeable')} value={upgradeable} color="var(--success)" />
        {/* #199: without this the queue reads as a healthy backlog. On the
            install that reported it, 67% of "wanted" had quietly given up and
            every item sat under the same badge. */}
        <SummaryCard
          icon={Ban}
          label={t('wanted.exhausted')}
          value={exhausted}
          color="var(--text-muted)"
        />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div data-testid="wanted-filter-status" className="flex gap-1.5">
          {STATUS_FILTERS.map((s) => {
            const isActive = (s === 'all' && !statusFilter) || statusFilter === s
            return (
              <button
                key={s}
                onClick={() => { onStatusFilter(s === 'all' ? undefined : s) }}
                className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
                style={{
                  backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--bg-surface)',
                  color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                  border: `1px solid ${isActive ? 'var(--accent-dim)' : 'var(--border)'}`,
                }}
              >
                {t(STATUS_I18N[s] ?? s, s)}
              </button>
            )
          })}
        </div>
        <div className="flex gap-1.5">
          {TYPE_FILTERS.map((tf) => {
            const isActive = (tf === 'all' && !typeFilter) || typeFilter === tf
            return (
              <button
                key={tf}
                onClick={() => { onTypeFilter(tf === 'all' ? undefined : tf) }}
                className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
                style={{
                  backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--bg-surface)',
                  color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                  border: `1px solid ${isActive ? 'var(--accent-dim)' : 'var(--border)'}`,
                }}
              >
                {t(TYPE_I18N[tf] ?? tf, tf)}
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
                  onClick={() => { onSubtitleTypeFilter(st === 'all' ? undefined : st) }}
                  className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
                  style={{
                    backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--bg-surface)',
                    color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                    border: `1px solid ${isActive ? 'var(--accent-dim)' : 'var(--border)'}`,
                  }}
                >
                  {t(SUBTITLE_TYPE_I18N[st] ?? st, st)}
                  {st === 'forced' && ` (${forcedCount})`}
                </button>
              )
            })}
          </div>
        )}
        {availableLanguages.length > 1 && (
          <div className="flex gap-1.5">
            <button
              onClick={() => { onLanguageFilter(undefined) }}
              className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
              style={{
                backgroundColor: !languageFilter ? 'var(--accent-bg)' : 'var(--bg-surface)',
                color: !languageFilter ? 'var(--accent)' : 'var(--text-secondary)',
                border: `1px solid ${!languageFilter ? 'var(--accent-dim)' : 'var(--border)'}`,
              }}
            >
              {t('wanted.all_langs')}
            </button>
            {availableLanguages.map((lang) => {
              const isActive = languageFilter === lang
              return (
                <button
                  key={lang}
                  onClick={() => { onLanguageFilter(isActive ? undefined : lang) }}
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
            onClick={() => { onUpgradeFilter(!upgradeFilter) }}
            className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
            style={{
              backgroundColor: upgradeFilter ? 'rgba(16,185,129,0.1)' : 'var(--bg-surface)',
              color: upgradeFilter ? 'var(--success)' : 'var(--text-secondary)',
              border: `1px solid ${upgradeFilter ? 'var(--success)' : 'var(--border)'}`,
            }}
          >
            {t('wanted.upgrades_only', { count: upgradeable })}
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
            onChange={(e) => onSearchText(e.target.value)}
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
            onChange={(e) => { onSortBy(e.target.value) }}
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
            onClick={() => onSortDir(sortDir === 'asc' ? 'desc' : 'asc')}
            className="p-1.5 rounded-md transition-all duration-150"
            title={sortDir === 'asc' ? t('wanted.sort_asc') : t('wanted.sort_desc')}
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

      {/* FilterBar (includes preset menu) */}
      <FilterBar
        scope={scope}
        filters={wantedFilters}
        activeFilters={activeFilters}
        onFiltersChange={onFiltersChange}
        onPresetLoad={handlePresetLoad}
      />
    </>
  )
}
