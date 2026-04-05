import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AttentionBanner } from './AttentionBanner'
import { useJobs } from '@/hooks/useSystemApi'
import { truncatePath, formatRelativeTime } from '@/lib/utils'

const FEED_LIMIT = 20
const DOT_COLOR: Record<string, string> = {
  completed: 'var(--success)',
  failed: 'var(--error)',
}

function dotColor(status: string): string {
  return DOT_COLOR[status] ?? 'var(--accent)'
}

export function ActivityFeed() {
  const { t } = useTranslation('dashboard')
  const { data: jobsData } = useJobs(1, FEED_LIMIT, undefined, 15000)

  const jobs = jobsData?.data ?? []
  const total = jobsData?.total ?? 0

  return (
    <div
      data-testid="activity-feed"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        flex: 1,
        minHeight: 0,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 14px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: '11px',
            fontWeight: 700,
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.4px',
          }}
        >
          {t('feed.title')}
        </span>
        <Link
          data-testid="feed-view-all"
          to="/activity"
          style={{ fontSize: '11px', color: 'var(--accent)', textDecoration: 'none' }}
        >
          {t('feed.viewAll')} →
        </Link>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 10px' }}>
        <AttentionBanner />

        {jobs.length === 0 ? (
          <div
            data-testid="feed-empty"
            style={{
              padding: '24px 0',
              textAlign: 'center',
              fontSize: '13px',
              color: 'var(--text-muted)',
            }}
          >
            {t('feed.empty')}
          </div>
        ) : (
          <>
            {jobs.map((job) => (
              <div
                key={job.id}
                data-testid={`feed-item-${job.id}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '5px 4px',
                  borderRadius: '4px',
                }}
              >
                <span
                  data-testid={`feed-dot-${job.id}`}
                  data-status={job.status}
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    background: dotColor(job.status),
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    flex: 1,
                    fontSize: '12px',
                    color: 'var(--text-secondary)',
                    fontFamily: 'var(--font-mono)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={job.file_path}
                >
                  {truncatePath(job.file_path)}
                </span>
                {job.created_at && (
                  <span
                    style={{
                      fontSize: '10px',
                      color: 'var(--text-muted)',
                      whiteSpace: 'nowrap',
                      flexShrink: 0,
                    }}
                  >
                    {formatRelativeTime(job.created_at)}
                  </span>
                )}
              </div>
            ))}

            {total > FEED_LIMIT && (
              <div
                data-testid="feed-more-events"
                style={{
                  textAlign: 'center',
                  padding: '8px 0',
                  fontSize: '11px',
                  color: 'var(--text-muted)',
                }}
              >
                ··· {total - FEED_LIMIT} {t('feed.moreEvents')}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
