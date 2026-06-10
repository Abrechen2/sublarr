import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ChevronRight, Search, SkipForward, Check } from 'lucide-react'
import { useWantedItems, useSearchWantedItem, useUpdateWantedStatus } from '@/hooks/useWantedApi'
import type { WantedItem } from '@/types/wanted'

const MAX_ITEMS = 5
const LOW_SCORE_THRESHOLD = 50

interface ActionBtnProps {
  readonly testId: string
  readonly onClick: () => void
  readonly label: string
  readonly variant?: 'primary' | 'ghost'
  readonly icon?: React.ReactNode
}

function ActionBtn({ testId, onClick, label, variant = 'ghost', icon }: ActionBtnProps) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '3px',
        padding: '3px 8px',
        fontSize: '10px',
        fontWeight: variant === 'primary' ? 600 : 500,
        borderRadius: '5px',
        border: variant === 'primary' ? '1px solid var(--accent)' : '1px solid var(--border)',
        background: variant === 'primary' ? 'var(--accent)' : 'transparent',
        color: variant === 'primary' ? 'var(--bg-primary)' : 'var(--text-secondary)',
        cursor: 'pointer',
        whiteSpace: 'nowrap',
      }}
    >
      {icon}
      {label}
    </button>
  )
}

export function AttentionBanner() {
  const { t } = useTranslation('dashboard')
  const { data, isLoading } = useWantedItems(1, MAX_ITEMS * 2)
  const searchMutation = useSearchWantedItem()
  const statusMutation = useUpdateWantedStatus()

  const allFetched: WantedItem[] = data?.data ?? []
  const failedItems = allFetched.filter((item) => item.status === 'failed')
  // current_score > 0 means a subtitle exists but scored poorly (upgrade candidate)
  const lowScoreItems = allFetched.filter(
    (item) =>
      item.current_score > 0 && item.current_score < LOW_SCORE_THRESHOLD && item.status !== 'failed',
  )

  const allItems = [...failedItems, ...lowScoreItems].slice(0, MAX_ITEMS)

  if (isLoading || allItems.length === 0) return null

  const total = allItems.length

  return (
    <div
      data-testid="attention-banner"
      style={{
        background: 'color-mix(in srgb, var(--warning) 6%, transparent)',
        border: '1px solid color-mix(in srgb, var(--warning) 30%, transparent)',
        borderRadius: 'var(--radius-md, 8px)',
        padding: '8px 12px',
        marginBottom: '4px',
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '6px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--warning)' }}>
            ⚠ {t('attention.title')}
          </span>
          <span
            data-testid="attention-count"
            style={{
              fontSize: '10px',
              fontWeight: 600,
              color: 'var(--warning)',
              background: 'color-mix(in srgb, var(--warning) 12%, transparent)',
              padding: '0 6px',
              borderRadius: '10px',
            }}
          >
            {total}
          </span>
        </div>
        <Link
          data-testid="attention-view-all"
          to="/wanted"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '3px',
            fontSize: '11px',
            color: 'var(--accent)',
            textDecoration: 'none',
          }}
        >
          {t('attention.viewAll')} <ChevronRight size={11} />
        </Link>
      </div>

      {/* Item rows */}
      {allItems.map((item, index) => {
        const isFailed = item.status === 'failed'
        const episodeLabel = item.season_episode || null

        return (
          <div
            key={item.id}
            data-testid={`attention-item-${item.id}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '4px 0',
              borderTop:
                index === 0
                  ? 'none'
                  : '1px solid color-mix(in srgb, var(--warning) 15%, transparent)',
            }}
          >
            <span
              data-testid={`attention-title-${item.id}`}
              style={{
                flex: 1,
                fontSize: '12px',
                fontWeight: 500,
                color: 'var(--text-primary)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {item.title}
              {episodeLabel && (
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '5px' }}>
                  {episodeLabel}
                </span>
              )}
            </span>
            <span
              data-testid={`attention-reason-${item.id}`}
              style={{ fontSize: '10px', color: 'var(--text-muted)', flexShrink: 0 }}
            >
              {isFailed ? t('attention.reasonFailed') : `Score ${item.current_score}`}
            </span>
            <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
              {isFailed ? (
                <>
                  <ActionBtn
                    testId={`attention-search-${item.id}`}
                    onClick={() => searchMutation.mutate(item.id)}
                    label={t('attention.search')}
                    icon={<Search size={10} />}
                    variant="primary"
                  />
                  <ActionBtn
                    testId={`attention-skip-${item.id}`}
                    onClick={() => statusMutation.mutate({ itemId: item.id, status: 'skipped' })}
                    label={t('attention.skip')}
                    icon={<SkipForward size={10} />}
                  />
                </>
              ) : (
                <>
                  <ActionBtn
                    testId={`attention-find-better-${item.id}`}
                    onClick={() => searchMutation.mutate(item.id)}
                    label={t('attention.findBetter')}
                    icon={<Search size={10} />}
                    variant="primary"
                  />
                  <ActionBtn
                    testId={`attention-accept-${item.id}`}
                    onClick={() => statusMutation.mutate({ itemId: item.id, status: 'accepted' })}
                    label={t('attention.accept')}
                    icon={<Check size={10} />}
                  />
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
