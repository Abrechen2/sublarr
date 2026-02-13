import { useJobs, useBatchStatus } from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ProgressBar } from '@/components/shared/ProgressBar'
import { truncatePath } from '@/lib/utils'
import { Loader2 } from 'lucide-react'

export function QueuePage() {
  const { data: activeJobs } = useJobs(1, 20, 'running')
  const { data: queuedJobs } = useJobs(1, 20, 'queued')
  const { data: batch } = useBatchStatus()

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Queue</h1>

      {/* Batch Status */}
      {batch?.running && (
        <div
          className="rounded-xl p-5 shadow-sm"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Loader2 size={18} className="animate-spin" style={{ color: 'var(--accent)' }} />
            <h2 className="text-sm font-semibold">Batch Processing</h2>
          </div>
          <ProgressBar value={batch.processed} max={batch.total} className="mb-3" />
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 text-sm">
            <div>
              <span style={{ color: 'var(--text-secondary)' }}>Total: </span>
              <span className="font-mono">{batch.total}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-secondary)' }}>Processed: </span>
              <span className="font-mono">{batch.processed}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-secondary)' }}>Succeeded: </span>
              <span className="font-mono" style={{ color: 'var(--success)' }}>{batch.succeeded}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-secondary)' }}>Failed: </span>
              <span className="font-mono" style={{ color: 'var(--error)' }}>{batch.failed}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-secondary)' }}>Skipped: </span>
              <span className="font-mono">{batch.skipped}</span>
            </div>
          </div>
          {batch.current_file && (
            <div className="mt-3 text-xs truncate" style={{ color: 'var(--text-secondary)' }}>
              Current: {truncatePath(batch.current_file, 80)}
            </div>
          )}
        </div>
      )}

      {/* Active Jobs */}
      <div
        className="rounded-xl overflow-hidden shadow-sm"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="px-5 py-4" style={{ borderBottom: '1px solid var(--border)' }}>
          <h2 className="text-sm font-semibold">
            Running ({activeJobs?.data?.length ?? 0})
          </h2>
        </div>
        <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {activeJobs?.data?.length ? (
            activeJobs.data.map((job) => (
              <div key={job.id} className="px-5 py-3 flex items-center gap-3">
                <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent)' }} />
                <span className="text-sm flex-1 truncate" title={job.file_path}>
                  {truncatePath(job.file_path)}
                </span>
                <StatusBadge status="running" />
              </div>
            ))
          ) : (
            <div className="px-5 py-6 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
              No active translations
            </div>
          )}
        </div>
      </div>

      {/* Queued Jobs */}
      <div
        className="rounded-xl overflow-hidden shadow-sm"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="px-5 py-4" style={{ borderBottom: '1px solid var(--border)' }}>
          <h2 className="text-sm font-semibold">
            Queued ({queuedJobs?.data?.length ?? 0})
          </h2>
        </div>
        <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {queuedJobs?.data?.length ? (
            queuedJobs.data.map((job) => (
              <div key={job.id} className="px-5 py-3 flex items-center gap-3">
                <div className="w-4 h-4 rounded-full" style={{ border: '2px solid var(--warning)' }} />
                <span className="text-sm flex-1 truncate" title={job.file_path}>
                  {truncatePath(job.file_path)}
                </span>
                <StatusBadge status="queued" />
              </div>
            ))
          ) : (
            <div className="px-5 py-6 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
              No queued jobs
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
