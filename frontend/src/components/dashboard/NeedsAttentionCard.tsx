/**
 * NeedsAttentionCard — dashboard card listing wanted items that require manual action.
 *
 * - Warning-colored left border (4px --warning)
 * - Header: AlertTriangle icon + "Needs Attention" title + total count badge
 * - Each item row: title, episode info, reason badge, contextual action buttons
 *   - status === 'failed' (no match)  → Search + Skip
 *   - score < 50 (low quality match) → Find Better + Accept
 *   - fallback                        → Retry
 * - "View All" link at bottom → /activity
 * - Max 5 items shown
 */
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Search, SkipForward, RefreshCw, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useWantedItems, useSearchWantedItem, useUpdateWantedStatus } from '@/hooks/useWantedApi'

// ─── Types ────────────────────────────────────────────────────────────────────

interface WantedItem {
  readonly id: number
  readonly title: string
  readonly series_title: string
  readonly season_number: number | null
  readonly episode_number: number | null
  readonly status: string
  readonly score: number | null
  readonly file_path: string
}

type IssueType = 'failed' | 'low_score' | 'other'

function resolveIssueType(item: WantedItem): IssueType {
  if (item.status === 'failed') return 'failed'
  if (item.score !== null && item.score < 50) return 'low_score'
  return 'other'
}

// ─── Sub-components ───────────────────────────────────────────────────────────

interface ActionButtonProps {
  readonly testId: string
  readonly onClick: () => void
  readonly icon: React.ReactNode
  readonly label: string
  readonly variant?: 'primary' | 'ghost'
}

function ActionButton({ testId, onClick, icon, label, variant = 'ghost' }: ActionButtonProps) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      title={label}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        padding: '4px 8px',
        fontSize: '11px',
        fontWeight: 500,
        borderRadius: '5px',
        border: variant === 'primary' ? '1px solid var(--accent)' : '1px solid var(--border)',
        background: variant === 'primary' ? 'var(--accent-bg)' : 'transparent',
        color: variant === 'primary' ? 'var(--accent)' : 'var(--text-secondary)',
        cursor: 'pointer',
        whiteSpace: 'nowrap',
      }}
    >
      {icon}
      {label}
    </button>
  )
}

interface ItemRowProps {
  readonly item: WantedItem
  readonly onSearch: (id: number) => void
  readonly onSkip: (id: number) => void
  readonly onAccept: (id: number) => void
}

function ItemRow({ item, onSearch, onSkip, onAccept }: ItemRowProps) {
  const { t } = useTranslation('common')
  const issueType = resolveIssueType(item)

  const episodeLabel =
    item.season_number !== null && item.episode_number !== null
      ? `S${String(item.season_number).padStart(2, '0')}E${String(item.episode_number).padStart(2, '0')}`
      : null

  const reasonLabel =
    issueType === 'failed'
      ? t('needsAttention.reason.noMatch', 'No Match')
      : issueType === 'low_score'
        ? t('needsAttention.reason.lowScore', `Score ${item.score}`)
        : t('needsAttention.reason.error', 'Error')

  const reasonColor =
    issueType === 'failed'
      ? 'var(--error)'
      : issueType === 'low_score'
        ? 'var(--warning)'
        : 'var(--text-muted)'

  return (
    <div
      data-testid={`item-row-${item.id}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '8px 0',
        borderBottom: '1px solid var(--border)',
      }}
    >
      {/* Avatar / icon placeholder */}
      <div
        style={{
          width: '32px',
          height: '32px',
          borderRadius: '6px',
          background: 'var(--bg-primary)',
          border: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          color: reasonColor,
        }}
      >
        <AlertTriangle size={14} />
      </div>

      {/* Title + reason */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          data-testid={`item-title-${item.id}`}
          style={{
            fontSize: '13px',
            fontWeight: 600,
            color: 'var(--text-primary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {item.series_title}
          {episodeLabel && (
            <span
              style={{
                fontSize: '11px',
                fontWeight: 400,
                color: 'var(--text-muted)',
                marginLeft: '6px',
              }}
            >
              {episodeLabel}
            </span>
          )}
        </div>
        <span
          data-testid={`item-reason-${item.id}`}
          style={{
            display: 'inline-block',
            fontSize: '10px',
            fontWeight: 500,
            color: reasonColor,
            background: `color-mix(in srgb, ${reasonColor} 12%, transparent)`,
            padding: '1px 6px',
            borderRadius: '4px',
            marginTop: '2px',
          }}
        >
          {reasonLabel}
        </span>
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
        {issueType === 'failed' && (
          <>
            <ActionButton
              testId={`btn-search-${item.id}`}
              onClick={() => onSearch(item.id)}
              icon={<Search size={11} />}
              label={t('needsAttention.action.search', 'Search')}
              variant="primary"
            />
            <ActionButton
              testId={`btn-skip-${item.id}`}
              onClick={() => onSkip(item.id)}
              icon={<SkipForward size={11} />}
              label={t('needsAttention.action.skip', 'Skip')}
            />
          </>
        )}

        {issueType === 'low_score' && (
          <>
            <ActionButton
              testId={`btn-find-better-${item.id}`}
              onClick={() => onSearch(item.id)}
              icon={<Search size={11} />}
              label={t('needsAttention.action.findBetter', 'Find Better')}
              variant="primary"
            />
            <ActionButton
              testId={`btn-accept-${item.id}`}
              onClick={() => onAccept(item.id)}
              icon={<RefreshCw size={11} />}
              label={t('needsAttention.action.accept', 'Accept')}
            />
          </>
        )}

        {issueType === 'other' && (
          <ActionButton
            testId={`btn-retry-${item.id}`}
            onClick={() => onSearch(item.id)}
            icon={<RefreshCw size={11} />}
            label={t('needsAttention.action.retry', 'Retry')}
          />
        )}
      </div>
    </div>
  )
}

// ─── NeedsAttentionCard ───────────────────────────────────────────────────────

const MAX_ITEMS = 5

export function NeedsAttentionCard() {
  const { t } = useTranslation('common')
  const { data } = useWantedItems(1, MAX_ITEMS)
  const searchMutation = useSearchWantedItem()
  const statusMutation = useUpdateWantedStatus()

  // Filter to items that need attention: failed status or low score
  const allItems: WantedItem[] = data?.items ?? []
  const attentionItems = allItems
    .filter(item => item.status === 'failed' || (item.score !== null && item.score < 50))
    .slice(0, MAX_ITEMS)

  const total: number = data?.total ?? 0

  const handleSearch = (id: number) => searchMutation.mutate(id)
  const handleSkip = (id: number) => statusMutation.mutate({ itemId: id, status: 'skipped' })
  const handleAccept = (id: number) => statusMutation.mutate({ itemId: id, status: 'accepted' })

  return (
    <div
      data-testid="needs-attention-card"
      className={cn('needs-attention-card')}
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderLeft: '4px solid var(--warning)',
        borderRadius: 'var(--radius-lg, 12px)',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
      }}
    >
      {/* Header */}
      <div
        data-testid="needs-attention-header"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '4px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertTriangle
            data-testid="needs-attention-icon"
            size={16}
            style={{ color: 'var(--warning)', flexShrink: 0 }}
          />
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {t('needsAttention.title', 'Needs Attention')}
          </span>
          {total > 0 && (
            <span
              data-testid="needs-attention-count"
              style={{
                fontSize: '11px',
                fontWeight: 600,
                color: 'var(--warning)',
                background: 'color-mix(in srgb, var(--warning) 12%, transparent)',
                padding: '1px 7px',
                borderRadius: '10px',
              }}
            >
              {total}
            </span>
          )}
        </div>
      </div>

      {/* Item rows */}
      {attentionItems.length === 0 ? (
        <p
          style={{
            fontSize: '13px',
            color: 'var(--text-muted)',
            textAlign: 'center',
            padding: '16px 0',
            margin: 0,
          }}
        >
          {t('needsAttention.empty', 'No items need attention')}
        </p>
      ) : (
        attentionItems.map(item => (
          <ItemRow
            key={item.id}
            item={item}
            onSearch={handleSearch}
            onSkip={handleSkip}
            onAccept={handleAccept}
          />
        ))
      )}

      {/* View All link */}
      <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'flex-end' }}>
        <Link
          data-testid="view-all-link"
          to="/activity"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '12px',
            fontWeight: 500,
            color: 'var(--accent)',
            textDecoration: 'none',
          }}
        >
          {t('needsAttention.viewAll', 'View All')}
          <ChevronRight size={12} />
        </Link>
      </div>
    </div>
  )
}

export default NeedsAttentionCard
