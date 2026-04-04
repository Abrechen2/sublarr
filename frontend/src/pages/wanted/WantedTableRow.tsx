import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Search, RefreshCw, Eye, EyeOff, Play, Loader2, ChevronUp,
  CheckSquare, Square, Download, ScanSearch,
} from 'lucide-react'
import { StatusBadge, SubtitleTypeBadge } from '@/components/shared/StatusBadge'
import { formatRelativeTime, truncatePath } from '@/lib/utils'
import { FailureReasonRow } from '@/pages/Wanted'
import type { WantedSearchResponse } from '@/lib/types'
import { SubtitlePresencePills } from '@/pages/wanted/SubtitlePresencePills'

interface SearchResultsRowProps {
  results: WantedSearchResponse | null
  isLoading: boolean
  onBlacklist: (providerName: string, subtitleId: string, language: string) => void
  t: (key: string, opts?: Record<string, unknown>) => string
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

function SearchResultsRow({ results, isLoading, onBlacklist, t }: SearchResultsRowProps) {
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
    ...(results.target_results ?? []).map((r) => ({ ...r, _type: 'target' as const })),
    ...(results.source_results ?? []).map((r) => ({ ...r, _type: 'source' as const })),
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
                      <Search size={12} />
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

export interface WantedItem {
  id: number
  title: string
  file_path: string
  item_type: string
  status: string
  season_episode: string | null
  existing_sub: string
  embedded_languages: Array<{ lang: string; format: string }>
  target_language: string
  subtitle_type: string
  instance_name: string
  search_count: number
  last_search_at: string | null
  added_at: string | null
  upgrade_candidate: number
  error: string
  retry_after: string | null
}

export interface WantedTableRowProps {
  item: WantedItem
  itemIndex: number
  isSelected: boolean
  expandedItem: number | null
  sourceLanguage: string
  searchingItems: Set<number>
  searchResults: Record<number, WantedSearchResponse>
  extractingItemId: number | null
  searchPending: boolean
  processPending: boolean
  retranslatePending: boolean
  translationEnabled: boolean
  visibleIds: number[]
  scope: 'wanted'
  onToggleItem: (scope: 'wanted', id: number, idx: number, shift: boolean, ids: number[]) => void
  onSearch: (itemId: number) => void
  onProcess: (itemId: number) => void
  onExtract: (itemId: number, targetLanguage?: string) => void
  onRetranslate: (itemId: number) => void
  onUpdateStatus: (itemId: number, status: string) => void
  onPreview: (filePath: string) => void
  onInteractiveSearch: (item: { id: number; title: string }) => void
  onBlacklist: (itemId: number, providerName: string, subtitleId: string, language: string) => void
}

function deriveSubtitlePath(mediaPath: string, lang: string, format: string): string {
  const lastDot = mediaPath.lastIndexOf('.')
  const base = lastDot > 0 ? mediaPath.substring(0, lastDot) : mediaPath
  return `${base}.${lang}.${format}`
}

export function WantedTableRow({
  item,
  itemIndex,
  isSelected,
  expandedItem,
  sourceLanguage,
  searchingItems,
  searchResults,
  extractingItemId,
  searchPending,
  processPending,
  retranslatePending,
  translationEnabled,
  visibleIds,
  scope,
  onToggleItem,
  onSearch,
  onProcess,
  onExtract,
  onRetranslate,
  onUpdateStatus,
  onPreview,
  onInteractiveSearch,
  onBlacklist,
}: WantedTableRowProps) {
  const { t } = useTranslation('library')

  return (
    <Fragment key={item.id}>
      <tr
        data-testid="wanted-item"
        className="transition-colors duration-100"
        style={{ borderBottom: '1px solid var(--border)', animationDelay: `${Math.min(itemIndex * 30, 300)}ms` }}
        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)')}
        onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
      >
        <td className="px-3 py-2.5 w-8">
          <button
            onClick={(e) => {
              const idx = visibleIds.indexOf(item.id)
              onToggleItem(scope, item.id, idx, e.shiftKey, visibleIds)
            }}
            className="p-0.5"
            style={{ color: 'var(--text-muted)' }}
          >
            {isSelected ? (
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
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-1.5">
              <StatusBadge status={item.status} />
              <SubtitleTypeBadge subtitleType={item.subtitle_type} />
            </div>
            {item.status === 'failed' && (
              <FailureReasonRow
                error={item.error}
                retryAfter={item.retry_after}
                searchCount={item.search_count}
              />
            )}
          </div>
        </td>
        <td className="px-3 py-2.5 hidden sm:table-cell">
          <SubtitlePresencePills
            existingSub={item.existing_sub}
            targetLanguage={item.target_language}
            sourceLanguage={sourceLanguage}
            embeddedLanguages={item.embedded_languages ?? []}
            upgradeCandidate={item.upgrade_candidate === 1}
          />
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
                onClick={() => onPreview(deriveSubtitlePath(item.file_path, item.target_language, item.existing_sub))}
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
              data-testid="wanted-search-btn"
              onClick={() => onSearch(item.id)}
              disabled={searchPending && expandedItem === item.id}
              className="p-1 rounded transition-colors duration-150"
              title={t('wanted.search_providers')}
              style={{ color: expandedItem === item.id ? 'var(--accent)' : 'var(--text-muted)' }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
              onMouseLeave={(e) => {
                if (expandedItem !== item.id) e.currentTarget.style.color = 'var(--text-muted)'
              }}
            >
              {searchPending && expandedItem === item.id
                ? <Loader2 size={14} className="animate-spin" />
                : expandedItem === item.id ? <ChevronUp size={14} /> : <Search size={14} />
              }
            </button>
            {(item.existing_sub === 'embedded_ass' || item.existing_sub === 'embedded_srt') && (
              <button
                onClick={() => onExtract(item.id, item.target_language)}
                disabled={extractingItemId === item.id}
                className="p-1 rounded transition-colors duration-150"
                title={t('wanted.extract_embedded')}
                style={{ color: 'var(--text-muted)' }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
              >
                {extractingItemId === item.id ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
              </button>
            )}
            <button
              onClick={() => onInteractiveSearch({ id: item.id, title: item.title })}
              className="p-1 rounded transition-colors duration-150"
              title="Interaktive Suche"
              style={{ color: 'var(--text-muted)' }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
            >
              <ScanSearch size={14} />
            </button>
            <button
              data-testid="wanted-process-btn"
              onClick={() => onProcess(item.id)}
              disabled={processPending || item.status === 'searching'}
              className="p-1 rounded transition-colors duration-150"
              title={t('wanted.download_translate')}
              style={{ color: 'var(--text-muted)' }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--success)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
            >
              <Play size={14} />
            </button>
            {translationEnabled && (
              <button
                onClick={() => onRetranslate(item.id)}
                disabled={retranslatePending}
                className="p-1 rounded transition-colors duration-150"
                title={t('wanted.re_translate')}
                style={{ color: 'var(--text-muted)' }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--warning)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
              >
                <RefreshCw size={14} />
              </button>
            )}
            <button
              onClick={() => onUpdateStatus(item.id, item.status === 'ignored' ? 'wanted' : 'ignored')}
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
          isLoading={searchingItems.has(item.id)}
          t={t}
          onBlacklist={(providerName, subtitleId, language) =>
            onBlacklist(item.id, providerName, subtitleId, language)
          }
        />
      )}
    </Fragment>
  )
}
