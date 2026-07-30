import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'

function stripLangSuffix(title: string): string {
  return title.replace(/\s*\[[A-Z]{2,3}\]\s*$/, '').trim()
}
import { CheckSquare, Square, MinusSquare } from 'lucide-react'
import { formatRelativeTime, truncatePath } from '@/lib/utils'
import { StatusBadge, SubtitleTypeBadge } from '@/components/shared/StatusBadge'
import { SubtitlePresencePills } from '@/pages/wanted/SubtitlePresencePills'
import {
  WantedRowActions,
  SearchResultsRow,
  FailureReasonRow,
} from '@/pages/wanted/WantedTableRow'
import type { WantedGroup, WantedSearchResponse } from '@/types/wanted'

interface WantedGroupedRowProps {
  group: WantedGroup
  groupIndex: number
  expandedItem: number | null
  sourceLanguage: string
  searchingItems: Set<number>
  searchResults: Record<number, WantedSearchResponse>
  extractingItemId: number | null
  processPending: boolean
  retranslatePending: boolean
  translationEnabled: boolean
  processingItemId: number | null
  isSelected: (id: number) => boolean
  onToggleGroup: (itemIds: number[], shiftKey: boolean) => void
  onExpand: (itemId: number | null) => void
  onProcess: (itemId: number) => void
  onExtract: (itemId: number, targetLanguage?: string) => void
  onRetranslate: (itemId: number) => void
  onUpdateStatus: (itemId: number, status: string) => void
  onPreview: (filePath: string) => void
  onInteractiveSearch: (item: { id: number; title: string }) => void
  onDryRun: (item: { id: number; title: string }) => void
  onBlacklist: (itemId: number, providerName: string, subtitleId: string, language: string) => void
}

export function WantedGroupedRow({
  group,
  groupIndex,
  expandedItem,
  sourceLanguage,
  searchingItems,
  searchResults,
  extractingItemId,
  processPending,
  retranslatePending,
  translationEnabled,
  processingItemId,
  isSelected,
  onToggleGroup,
  onExpand,
  onProcess,
  onExtract,
  onRetranslate,
  onUpdateStatus,
  onPreview,
  onInteractiveSearch,
  onDryRun,
  onBlacklist,
}: WantedGroupedRowProps) {
  const { t } = useTranslation('library')
  const lastIdx = group.languages.length - 1
  const allSelected = group.languages.every((l) => isSelected(l.id))
  const someSelected = group.languages.some((l) => isSelected(l.id))
  const selectionState: 'all' | 'some' | 'none' = allSelected ? 'all' : someSelected ? 'some' : 'none'
  const earliestAdded = group.languages.reduce<string | null>(
    (min, item) => (!min || (item.added_at && item.added_at < min) ? item.added_at : min),
    null
  )

  return (
    <Fragment>
      {group.languages.map((item, langIdx) => {
        const isFirst = langIdx === 0
        const isLast = langIdx === lastIdx

        const restingBg = isFirst ? 'var(--bg-elevated)' : 'transparent'

        return (
          <Fragment key={item.id}>
            <tr
              data-testid="wanted-item"
              className="transition-colors duration-100"
              style={{
                borderBottom: isLast
                  ? '1px solid var(--border)'
                  : '1px dashed color-mix(in srgb, var(--border) 50%, transparent)',
                animationDelay: `${Math.min(groupIndex * 30, 300)}ms`,
                cursor: 'pointer',
                backgroundColor: restingBg,
              }}
              onClick={(e) => {
                if ((e.target as HTMLElement).closest('button')) return
                onExpand(expandedItem === item.id ? null : item.id)
              }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)')}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = restingBg)}
            >
              {/* Checkbox — first sub-row only */}
              <td
                className="px-3 py-2.5 w-8"
                style={{
                  verticalAlign: 'top',
                  borderLeft: isFirst
                    ? '2px solid #3730a3'
                    : '2px solid rgba(55, 48, 163, 0.18)',
                }}
              >
                {isFirst && (
                  <button
                    onClick={(e) =>
                      onToggleGroup(
                        group.languages.map((l) => l.id),
                        e.shiftKey
                      )
                    }
                    className="p-0.5"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {selectionState === 'all' ? (
                      <CheckSquare size={14} style={{ color: 'var(--accent)' }} />
                    ) : selectionState === 'some' ? (
                      <MinusSquare size={14} style={{ color: 'var(--accent)' }} />
                    ) : (
                      <Square size={14} />
                    )}
                  </button>
                )}
              </td>

              {/* Title — first sub-row only */}
              <td className="px-3 py-2.5" title={group.file_path}>
                {isFirst && (
                  <div className="flex items-center gap-1.5">
                    <span
                      className="truncate max-w-xs text-sm"
                      style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                    >
                      {stripLangSuffix(group.title) || truncatePath(group.file_path)}
                    </span>
                    {group.instance_name && (
                      <span
                        className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium"
                        style={{
                          backgroundColor: 'var(--bg-surface)',
                          color: 'var(--text-secondary)',
                          border: '1px solid var(--border)',
                        }}
                      >
                        {group.instance_name}
                      </span>
                    )}
                  </div>
                )}
              </td>

              {/* S/E — first sub-row only */}
              <td className="px-3 py-2.5">
                {isFirst && (
                  <span
                    className="text-xs"
                    style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
                  >
                    {group.season_episode || (group.item_type === 'movie' ? t('wanted.movie') : '—')}
                  </span>
                )}
              </td>

              {/* Language badge + Status — per sub-row */}
              <td className="px-3 py-2.5">
                <div className="flex flex-col gap-0.5">
                  <div className="flex items-center gap-1.5">
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

              {/* Existing subtitle pills — per sub-row */}
              <td className="px-3 py-2.5 hidden sm:table-cell">
                <SubtitlePresencePills
                  existingSub={item.existing_sub}
                  targetLanguage={item.target_language}
                  sourceLanguage={sourceLanguage}
                  embeddedLanguages={item.embedded_languages ?? []}
                  upgradeCandidate={item.upgrade_candidate === 1}
                />
              </td>

              {/* Search count — per sub-row */}
              <td
                className="px-3 py-2.5 text-xs tabular-nums hidden md:table-cell"
                style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
              >
                {item.search_count}
              </td>

              {/* Last search — per sub-row */}
              <td
                className="px-3 py-2.5 text-xs tabular-nums hidden lg:table-cell"
                style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
              >
                {item.last_search_at ? formatRelativeTime(item.last_search_at) : t('wanted.never')}
              </td>

              {/* Added — first sub-row only (earliest across all languages) */}
              <td
                className="px-3 py-2.5 text-xs tabular-nums hidden lg:table-cell"
                style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
              >
                {isFirst && earliestAdded ? formatRelativeTime(earliestAdded) : ''}
              </td>

              {/* Actions — per sub-row */}
              <td
                className="px-4 py-2.5 text-right"
                style={{ position: 'sticky', right: 0, backgroundColor: 'var(--bg-elevated)' }}
              >
                <WantedRowActions
                  item={item}
                  processingItemId={processingItemId}
                  extractingItemId={extractingItemId}
                  processPending={processPending}
                  retranslatePending={retranslatePending}
                  translationEnabled={translationEnabled}
                  onProcess={onProcess}
                  onExtract={onExtract}
                  onRetranslate={onRetranslate}
                  onUpdateStatus={onUpdateStatus}
                  onPreview={onPreview}
                  onInteractiveSearch={onInteractiveSearch}
                  onDryRun={onDryRun}
                />
              </td>
            </tr>

            {/* Expandable search results for this language item */}
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
      })}
    </Fragment>
  )
}
