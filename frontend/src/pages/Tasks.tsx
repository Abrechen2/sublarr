import { useTranslation } from 'react-i18next'
import { Play, Loader2, Clock, CheckCircle, XCircle, Timer } from 'lucide-react'
import { useTasks, useTriggerTask } from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'
import type { SchedulerTask } from '@/lib/types'

function formatRelativeTime(iso: string | null, t: (key: string, opts?: Record<string, unknown>) => string): string {
  if (!iso) return t('tasks.never')
  const date = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return t('time.just_now')
  if (diffMin < 60) return t('time.minutes_ago', { count: diffMin })
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return t('time.hours_ago', { count: diffH })
  const diffD = Math.floor(diffH / 24)
  return t('time.days_ago', { count: diffD })
}

function formatInterval(hours: number | null, t: (key: string, opts?: Record<string, unknown>) => string): string {
  if (!hours) return t('tasks.manual')
  if (hours < 1) {
    const minutes = Math.round(hours * 60)
    return t('tasks.every_minutes', { count: minutes })
  }
  if (hours === 1) return t('tasks.every_hour')
  if (hours === 24) return t('tasks.every_day')
  return t('tasks.every_hours', { count: hours })
}

function TaskCard({ task }: { task: SchedulerTask }) {
  const { t } = useTranslation('common')
  const triggerTask = useTriggerTask()

  const handleRunNow = () => {
    triggerTask.mutate(task.name, {
      onSuccess: () => toast(t('tasks.triggered', { name: task.display_name }), 'success'),
      onError: () => toast(t('tasks.trigger_failed', { name: task.display_name }), 'error'),
    })
  }

  const isTriggering = triggerTask.isPending && triggerTask.variables === task.name

  return (
    <div
      className="rounded-lg p-5 transition-all duration-200"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
      }}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          {/* Status indicator */}
          <div
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{
              backgroundColor: task.running
                ? 'var(--success)'
                : task.enabled
                  ? 'var(--text-muted)'
                  : 'var(--error)',
              animation: task.running ? 'dotGlow 2s ease-in-out infinite' : 'none',
            }}
          />
          <div>
            <h3
              className="text-sm font-semibold"
              style={{ color: 'var(--text-primary)' }}
            >
              {task.display_name}
            </h3>
            <span
              className="text-xs"
              style={{ color: task.running ? 'var(--success)' : 'var(--text-muted)' }}
            >
              {task.running ? t('tasks.running') : task.enabled ? t('tasks.idle') : t('status.disabled')}
            </span>
          </div>
        </div>

        {/* Run Now button */}
        <button
          onClick={handleRunNow}
          disabled={task.running || isTriggering}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
          style={{
            backgroundColor: 'var(--accent-bg)',
            color: 'var(--accent)',
            border: '1px solid var(--accent-dim)',
          }}
        >
          {isTriggering ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Play size={13} />
          )}
          {t('tasks.run_now')}
        </button>
      </div>

      {/* Details grid */}
      <div className="grid grid-cols-2 gap-3">
        {/* Last run */}
        <div className="flex items-center gap-2">
          <CheckCircle size={13} style={{ color: 'var(--text-muted)' }} />
          <div>
            <div
              className="text-[10px] uppercase tracking-wide font-medium"
              style={{ color: 'var(--text-muted)' }}
            >
              {t('tasks.last_run')}
            </div>
            <div
              className="text-xs"
              style={{ color: 'var(--text-secondary)' }}
            >
              {formatRelativeTime(task.last_run, t)}
            </div>
          </div>
        </div>

        {/* Next run */}
        <div className="flex items-center gap-2">
          <Clock size={13} style={{ color: 'var(--text-muted)' }} />
          <div>
            <div
              className="text-[10px] uppercase tracking-wide font-medium"
              style={{ color: 'var(--text-muted)' }}
            >
              {t('tasks.next_run')}
            </div>
            <div
              className="text-xs"
              style={{ color: 'var(--text-secondary)' }}
            >
              {task.next_run
                ? formatRelativeTime(task.next_run, t)
                : task.interval_hours
                  ? t('tasks.pending')
                  : t('tasks.manual')}
            </div>
          </div>
        </div>

        {/* Interval */}
        <div className="flex items-center gap-2">
          <Timer size={13} style={{ color: 'var(--text-muted)' }} />
          <div>
            <div
              className="text-[10px] uppercase tracking-wide font-medium"
              style={{ color: 'var(--text-muted)' }}
            >
              {t('tasks.interval')}
            </div>
            <div
              className="text-xs"
              style={{ color: 'var(--text-secondary)' }}
            >
              {formatInterval(task.interval_hours, t)}
            </div>
          </div>
        </div>

        {/* Enabled */}
        <div className="flex items-center gap-2">
          {task.enabled ? (
            <CheckCircle size={13} style={{ color: 'var(--success)' }} />
          ) : (
            <XCircle size={13} style={{ color: 'var(--error)' }} />
          )}
          <div>
            <div
              className="text-[10px] uppercase tracking-wide font-medium"
              style={{ color: 'var(--text-muted)' }}
            >
              {t('tasks.status')}
            </div>
            <div
              className="text-xs"
              style={{ color: task.enabled ? 'var(--success)' : 'var(--error)' }}
            >
              {task.enabled ? t('status.enabled') : t('status.disabled')}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function TasksSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="rounded-lg p-5 animate-pulse"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
          }}
        >
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: 'var(--bg-surface-hover)' }}
              />
              <div className="space-y-1.5">
                <div
                  className="h-4 w-32 rounded"
                  style={{ backgroundColor: 'var(--bg-surface-hover)' }}
                />
                <div
                  className="h-3 w-16 rounded"
                  style={{ backgroundColor: 'var(--bg-surface-hover)' }}
                />
              </div>
            </div>
            <div
              className="h-7 w-20 rounded-md"
              style={{ backgroundColor: 'var(--bg-surface-hover)' }}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            {[1, 2, 3, 4].map((j) => (
              <div key={j} className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded"
                  style={{ backgroundColor: 'var(--bg-surface-hover)' }}
                />
                <div className="space-y-1">
                  <div
                    className="h-2.5 w-14 rounded"
                    style={{ backgroundColor: 'var(--bg-surface-hover)' }}
                  />
                  <div
                    className="h-3 w-20 rounded"
                    style={{ backgroundColor: 'var(--bg-surface-hover)' }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function TasksPage() {
  const { t } = useTranslation('common')
  const { data, isLoading } = useTasks()

  const tasks = data?.tasks ?? []

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1>{t('tasks.title')}</h1>
      </div>

      {/* Tasks list */}
      {isLoading ? (
        <TasksSkeleton />
      ) : tasks.length === 0 ? (
        <div
          className="rounded-lg p-8 text-center"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            color: 'var(--text-muted)',
          }}
        >
          {t('tasks.no_tasks')}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {tasks.map((task) => (
            <TaskCard key={task.name} task={task} />
          ))}
        </div>
      )}
    </div>
  )
}
