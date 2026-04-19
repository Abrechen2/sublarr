import { Loader2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { TranslationActiveJob } from '@/lib/types'

function formatFilename(path: string): string {
  const parts = path.split(/[/\\]/)
  return parts[parts.length - 1] || path
}

function formatEta(
  seconds: number | null,
  t: (k: string, o?: Record<string, unknown>) => string,
): string {
  if (seconds === null) return t('translation.queue.eta_unknown')
  if (seconds < 60) return t('translation.queue.eta_seconds', { n: seconds })
  return t('translation.queue.eta_minutes', { n: Math.round(seconds / 60) })
}

export function ActiveJobCard({
  job,
  onCancel,
  cancelling = false,
}: {
  job: TranslationActiveJob
  onCancel: () => void
  cancelling?: boolean
}) {
  const { t } = useTranslation('settings')
  const costUsd = (job.cost_so_far_micro_usd / 1_000_000).toFixed(4)

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-mono text-sm">
              {formatFilename(job.file_path)}
            </span>
            <span className="rounded bg-elevated px-2 py-0.5 text-xs">
              {job.source_lang} → {job.target_lang}
            </span>
            <span className="rounded bg-elevated px-2 py-0.5 text-xs font-mono">
              {job.backend}
            </span>
          </div>
          <div className="mt-2 w-full">
            <div
              className="h-2 overflow-hidden rounded bg-elevated"
              role="progressbar"
              aria-valuenow={job.progress.pct}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full bg-accent transition-all"
                style={{ width: `${job.progress.pct}%` }}
              />
            </div>
            <div className="mt-1 flex justify-between text-xs text-muted">
              <span>
                {job.progress.done}/{job.progress.total} (
                {job.progress.pct.toFixed(1)}%)
              </span>
              <span>
                {formatEta(job.eta_seconds, t)} · ${costUsd}
              </span>
            </div>
          </div>
        </div>
        <button
          onClick={onCancel}
          disabled={cancelling || job.cancel_requested}
          className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-sm hover:bg-elevated disabled:opacity-50"
        >
          {cancelling || job.cancel_requested ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <X size={14} />
          )}
          {job.cancel_requested
            ? t('translation.queue.cancelling')
            : t('translation.queue.cancel')}
        </button>
      </div>
    </div>
  )
}
