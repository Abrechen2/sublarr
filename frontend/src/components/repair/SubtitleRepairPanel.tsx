/**
 * Restore subtitles damaged by the pre-1.6.6 HI-removal bug.
 *
 * Scanning is free — it compares each file against the hash recorded when it was
 * downloaded, and checks whether its .bak is provably the pristine original.
 * Only the restore itself may need to re-fetch from the provider, which is why
 * the two are separate actions and the download count is shown up front.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Download, HardDriveDownload, Loader2, ShieldCheck } from 'lucide-react'
import { scanDamaged, startRepair, getRepairStatus } from '@/api/system/repair'

export function SubtitleRepairPanel() {
  const { t } = useTranslation('common')
  const qc = useQueryClient()
  const [language, setLanguage] = useState('de')

  const { data: status } = useQuery({
    queryKey: ['repair-status'],
    queryFn: getRepairStatus,
    refetchInterval: (q) => (q.state.data?.running ? 2000 : false),
  })

  const {
    data: scan,
    isFetching: scanning,
    refetch: rescan,
  } = useQuery({
    queryKey: ['repair-scan', language],
    queryFn: () => scanDamaged(language || undefined),
    enabled: false,
  })

  const run = useMutation({
    mutationFn: (dry: boolean) => startRepair({ language: language || undefined, dry_run: dry }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['repair-status'] }),
  })

  const running = status?.running ?? false
  const pct = status && status.total > 0 ? Math.round((status.done / status.total) * 100) : 0

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2">
        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-danger" />
        <div>
          <h3 className="text-sm font-semibold text-primary">{t('repair.title')}</h3>
          <p className="text-xs text-muted mt-1">{t('repair.intro')}</p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <label className="text-xs text-muted">{t('repair.language')}</label>
        <input
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          placeholder="de"
          className="w-20 rounded border border-border bg-page px-2 py-1 text-xs"
        />
        <button
          onClick={() => rescan()}
          disabled={scanning || running}
          className="rounded px-3 py-1.5 text-xs font-medium border border-border disabled:opacity-50"
        >
          {scanning ? t('repair.scanning') : t('repair.scan')}
        </button>
      </div>

      {scan && (
        <div className="rounded-md border border-border bg-page p-3 space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-muted">{t('repair.damaged')}</span>
            <span className="font-semibold text-primary">{scan.damaged}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-muted">
              <ShieldCheck size={13} /> {t('repair.from_backup')}
            </span>
            <span className="text-primary">{scan.recoverable_from_backup}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-muted">
              <Download size={13} /> {t('repair.needs_download')}
            </span>
            <span className="text-primary">{scan.needs_download}</span>
          </div>
          {scan.already_repaired > 0 && (
            <div className="flex items-center justify-between">
              <span className="text-muted">{t('repair.already_repaired')}</span>
              <span className="text-primary">{scan.already_repaired}</span>
            </div>
          )}
          <p className="text-[11px] text-muted pt-1">{t('repair.safety')}</p>
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          onClick={() => run.mutate(true)}
          disabled={running || !scan?.damaged}
          className="rounded px-3 py-1.5 text-xs font-medium border border-border disabled:opacity-50"
        >
          {t('repair.dry_run')}
        </button>
        <button
          onClick={() => run.mutate(false)}
          disabled={running || !scan?.damaged}
          className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          <HardDriveDownload size={13} />
          {t('repair.start')}
        </button>
      </div>

      {status && (status.running || status.done > 0) && (
        <div className="rounded-md border border-border bg-page p-3 space-y-2 text-xs">
          <div className="flex items-center gap-2">
            {status.running && <Loader2 size={13} className="animate-spin" />}
            <span className="text-primary font-medium">
              {status.done} / {status.total}
              {status.dry_run ? ` — ${t('repair.dry_run')}` : ''}
            </span>
          </div>
          <div className="h-1.5 w-full rounded bg-border overflow-hidden">
            <div
              className="h-full rounded"
              style={{ width: `${pct}%`, backgroundColor: 'var(--accent)' }}
            />
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-muted pt-1">
            <span>{t('repair.restored')}: {status.repaired}</span>
            <span>{t('repair.from_backup')}: {status.from_bak}</span>
            <span>{t('repair.unprovable')}: {status.skipped_unprovable}</span>
            <span>{t('repair.failed')}: {status.failed}</span>
          </div>
          {status.quota_exhausted && (
            <p className="text-[11px] text-danger pt-1">{t('repair.quota_exhausted')}</p>
          )}
          {status.error && <p className="text-[11px] text-danger pt-1">{status.error}</p>}
        </div>
      )}
    </div>
  )
}
