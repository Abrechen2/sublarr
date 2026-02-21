/**
 * RecentActivityWidget -- Activity feed with recent jobs.
 *
 * Self-contained: fetches own data via useJobs(1, 10).
 * Shows job list with StatusBadge, file path, relative time, and View All link.
 */
import { useTranslation } from 'react-i18next'
import { Activity, CheckCircle2, XCircle } from 'lucide-react'
import { useJobs } from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { formatRelativeTime, truncatePath } from '@/lib/utils'

export default function RecentActivityWidget() {
  const { t } = useTranslation('dashboard')
  const { data: recentJobs } = useJobs(1, 10)

  return (
    <div className="flex flex-col h-full -mx-4 -mt-4">
      {/* View All link bar */}
      <div
        className="px-4 py-2 flex items-center justify-end shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <a
          href="/activity"
          className="text-xs font-medium"
          style={{ color: 'var(--accent)' }}
        >
          {t('recent_activity.view_all')} &rarr;
        </a>
      </div>

      {/* Job list */}
      <div
        className="flex-1 overflow-auto divide-y"
        style={{ borderColor: 'var(--border)' }}
      >
        {recentJobs?.data?.length ? (
          recentJobs.data.map((job) => (
            <div
              key={job.id}
              className="px-4 py-2 flex items-center gap-3 transition-colors duration-150"
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor =
                  'var(--bg-surface-hover)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'transparent'
              }}
            >
              {job.status === 'completed' ? (
                <CheckCircle2
                  size={14}
                  style={{ color: 'var(--success)' }}
                />
              ) : job.status === 'failed' ? (
                <XCircle size={14} style={{ color: 'var(--error)' }} />
              ) : (
                <Activity size={14} style={{ color: 'var(--accent)' }} />
              )}
              <span
                className="text-sm flex-1 truncate"
                title={job.file_path}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                }}
              >
                {truncatePath(job.file_path)}
              </span>
              <StatusBadge status={job.status} />
              <span
                className="text-xs tabular-nums hidden sm:inline"
                style={{
                  color: 'var(--text-muted)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                }}
              >
                {job.created_at ? formatRelativeTime(job.created_at) : ''}
              </span>
            </div>
          ))
        ) : (
          <div
            className="px-4 py-8 text-center text-sm"
            style={{ color: 'var(--text-secondary)' }}
          >
            {t('recent_activity.no_activity')}
          </div>
        )}
      </div>
    </div>
  )
}
