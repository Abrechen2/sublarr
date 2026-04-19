import { Check, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { TranslationRecentJob } from '@/lib/types'

function formatFilename(path: string): string {
  const parts = path.split(/[/\\]/)
  return parts[parts.length - 1] || path
}

export function RecentJobRow({ job }: { job: TranslationRecentJob }) {
  const { t: _t } = useTranslation('settings')
  const ok = job.status === 'ok'
  const costUsd = (job.cost_micro_usd / 1_000_000).toFixed(4)

  return (
    <div className="flex items-center gap-3 border-b border-border px-2 py-1.5 text-sm">
      {ok ? (
        <Check size={14} className="text-success" />
      ) : (
        <X size={14} className="text-error" />
      )}
      <span className="flex-1 truncate font-mono">
        {formatFilename(job.file_path)}
      </span>
      <span className="text-xs text-muted">
        {job.source_lang} → {job.target_lang}
      </span>
      <span className="text-xs font-mono text-muted">{job.backend}</span>
      <span className="text-xs text-muted">
        {job.duration_s.toFixed(1)}s · ${costUsd} · {job.lines} lines
      </span>
      {job.error_type && (
        <span className="text-xs text-error">{job.error_type}</span>
      )}
    </div>
  )
}
