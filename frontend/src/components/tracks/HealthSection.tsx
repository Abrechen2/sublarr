import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { scanEpisodeHealth, fixHealthIssue, rollbackHealthFix } from '@/api/subtitleHealth'
import type { EpisodeHealthResult, HealthIssue } from '@/lib/types'

const SEVERITY_CLASS: Record<string, string> = {
  confirmed: 'bg-red-500/15 text-red-400 border-red-500/30',
  suspicious: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  info: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
}

interface Props {
  episodeId: number
}

export function HealthSection({ episodeId }: Props) {
  const { t } = useTranslation('library')
  const [result, setResult] = useState<EpisodeHealthResult | null>(null)
  const [scanning, setScanning] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [lastFix, setLastFix] = useState<Map<number, number>>(new Map())

  const runScan = useCallback(async () => {
    setScanning(true)
    try {
      setResult(await scanEpisodeHealth(episodeId))
    } finally {
      setScanning(false)
    }
  }, [episodeId])

  const applyFix = useCallback(
    async (issue: HealthIssue, action: string) => {
      if (issue.id == null) return
      setBusyId(issue.id)
      try {
        const res = await fixHealthIssue(episodeId, issue.id, action)
        if (res.changed && res.fix_id != null) {
          setLastFix((m) => new Map(m).set(issue.id!, res.fix_id!))
          setResult((r) => (r ? { ...r, issues: r.issues.filter((i) => i.id !== issue.id) } : r))
        }
      } finally {
        setBusyId(null)
      }
    },
    [episodeId],
  )

  const undo = useCallback(
    async (fixId: number) => {
      await rollbackHealthFix(fixId)
      await runScan()
    },
    [runScan],
  )

  // Shadowed findings (embedded defect covered by a clean sidecar) are not
  // actionable — hide them so the fix doesn't reappear on every rescan.
  const visibleIssues = result ? result.issues.filter((i) => !i.shadowed) : []

  return (
    <div className="mt-4 border-t border-border pt-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-muted">{t('subtitle_health.title')}</h4>
        <button
          type="button"
          onClick={runScan}
          disabled={scanning}
          className="rounded-md border border-border px-3 py-1 text-sm hover:bg-surface disabled:opacity-50"
        >
          {scanning ? t('subtitle_health.scanning') : t('subtitle_health.scan')}
        </button>
      </div>

      {result && visibleIssues.length === 0 && (
        <p className="mt-2 text-sm text-emerald-400">{t('subtitle_health.healthy')}</p>
      )}

      {result && visibleIssues.length > 0 && (
        <ul className="mt-2 space-y-2">
          {visibleIssues.map((issue) => (
            <li
              key={`${issue.id}-${issue.target_path}-${issue.stream_index}`}
              className="rounded-md border border-border bg-surface p-3"
            >
              <div className="flex items-center gap-2">
                <span
                  className={`rounded px-2 py-0.5 text-xs border ${SEVERITY_CLASS[issue.severity] ?? ''}`}
                >
                  {t(`subtitle_health.severity.${issue.severity}`)}
                </span>
                <span className="text-sm font-medium">
                  {t(`subtitle_health.types.${issue.type}`)}
                </span>
                <span className="text-xs text-muted">
                  {issue.lang} · {issue.target_kind} · {issue.count}
                </span>
              </div>
              {issue.snippets.length > 0 && (
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap text-xs text-muted">
                  {issue.snippets[0]}
                </pre>
              )}
              <div className="mt-2 flex flex-wrap gap-2">
                {issue.fixable && issue.suggested_fix && (
                  <button
                    type="button"
                    disabled={busyId === issue.id}
                    onClick={() => applyFix(issue, issue.suggested_fix!)}
                    className="rounded-md bg-accent px-3 py-1 text-sm text-white hover:bg-accent-hover disabled:opacity-50"
                  >
                    {busyId === issue.id ? t('subtitle_health.fixing') : t('subtitle_health.fix')}
                  </button>
                )}
                {issue.id != null && lastFix.has(issue.id) && (
                  <button
                    type="button"
                    onClick={() => undo(lastFix.get(issue.id!)!)}
                    className="rounded-md border border-border px-3 py-1 text-sm hover:bg-surface"
                  >
                    {t('subtitle_health.rollback')}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
