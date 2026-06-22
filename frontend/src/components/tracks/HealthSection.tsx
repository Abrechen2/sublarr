import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  scanEpisodeHealth,
  fixHealthIssue,
  rollbackHealthFix,
  dismissHealthFinding,
} from '@/api/subtitleHealth'
import { autoSyncFile } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import type { EpisodeHealthResult, HealthIssue } from '@/lib/types'

const SEVERITY_CLASS: Record<string, string> = {
  confirmed: 'bg-red-500/15 text-red-400 border-red-500/30',
  suspicious: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  info: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
}

interface Props {
  episodeId: number
  onOpenEditor?: (filePath: string) => void
}

export function HealthSection({ episodeId, onOpenEditor }: Props) {
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

  const dropIssue = useCallback((id: number) => {
    setResult((r) => (r ? { ...r, issues: r.issues.filter((i) => i.id !== id) } : r))
  }, [])

  const applyFix = useCallback(
    async (issue: HealthIssue, action: string) => {
      if (issue.id == null) return
      setBusyId(issue.id)
      try {
        const res = await fixHealthIssue(episodeId, issue.id, action)
        if (res.changed && res.fix_id != null) {
          setLastFix((m) => new Map(m).set(issue.id!, res.fix_id!))
          dropIssue(issue.id)
        }
      } finally {
        setBusyId(null)
      }
    },
    [episodeId, dropIssue],
  )

  const dismiss = useCallback(
    async (issue: HealthIssue) => {
      if (issue.id == null) return
      setBusyId(issue.id)
      try {
        await dismissHealthFinding(issue.id)
        dropIssue(issue.id)
      } finally {
        setBusyId(null)
      }
    },
    [dropIssue],
  )

  const undo = useCallback(
    async (fixId: number) => {
      await rollbackHealthFix(fixId)
      await runScan()
    },
    [runScan],
  )

  const syncWithAudio = useCallback(
    async (issue: HealthIssue) => {
      try {
        await autoSyncFile(issue.target_path, result?.video_path)
        toast(t('subtitle_health.sync_started'), 'success')
      } catch {
        toast(t('subtitle_health.sync_failed'), 'error')
      }
    },
    [result, t],
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
          {visibleIssues.map((issue) => {
            const busy = busyId === issue.id
            const isEmbedded = issue.target_kind === 'embedded'
            const isSidecar = issue.target_kind === 'sidecar'
            return (
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
                      disabled={busy}
                      onClick={() => applyFix(issue, issue.suggested_fix!)}
                      className="rounded-md bg-accent px-3 py-1 text-sm text-white hover:bg-accent-hover disabled:opacity-50"
                    >
                      {busy ? t('subtitle_health.fixing') : t('subtitle_health.fix')}
                    </button>
                  )}
                  {/* Embedded defect: alternative that fixes the container itself
                      (the suggested fix only extracts a clean sidecar). */}
                  {isEmbedded && issue.fixable && issue.suggested_fix !== 'remux_track' && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => applyFix(issue, 'remux_track')}
                      className="rounded-md border border-border px-3 py-1 text-sm hover:bg-surface disabled:opacity-50"
                    >
                      {t('subtitle_health.remux_track')}
                    </button>
                  )}
                  {/* Timing issue on a sidecar: re-align to the audio. */}
                  {isSidecar && issue.type === 'timing_sanity' && (
                    <button
                      type="button"
                      onClick={() => syncWithAudio(issue)}
                      className="rounded-md border border-border px-3 py-1 text-sm hover:bg-surface"
                    >
                      {t('subtitle_health.sync_audio')}
                    </button>
                  )}
                  {/* Sidecar issue (e.g. timing): open the file in the editor. */}
                  {isSidecar && onOpenEditor && (
                    <button
                      type="button"
                      onClick={() => onOpenEditor(issue.target_path)}
                      className="rounded-md border border-border px-3 py-1 text-sm hover:bg-surface"
                    >
                      {t('subtitle_health.open_editor')}
                    </button>
                  )}
                  {issue.id != null && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => dismiss(issue)}
                      className="rounded-md border border-border px-3 py-1 text-sm text-muted hover:bg-surface disabled:opacity-50"
                    >
                      {t('subtitle_health.dismiss')}
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
            )
          })}
        </ul>
      )}
    </div>
  )
}
