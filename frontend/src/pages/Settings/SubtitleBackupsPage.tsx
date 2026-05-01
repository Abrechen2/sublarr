/**
 * SubtitleBackupsPage — bulk-management UI for the .bak.<ext> sidecars
 * left behind by subtitle_processor.apply_mods (HI removal, common-fixes,
 * credit removal, manual edits via the inline editor).
 *
 * Reachable only via a footer-link in CleanupSettings — backup management
 * is a maintenance task, not a daily operation, so it does not warrant a
 * top-level sidebar entry.
 *
 * The cleanup-rule "old_subtitle_baks" automates this in the background;
 * this page is for ad-hoc inspection + manual purges.
 */
import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Trash2, RotateCcw, Eye, AlertTriangle, ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { useSubtitleBackups, useCleanupSubtitleBackups } from '@/hooks/useLibraryApi'
import { undoProcessSubtitle, deleteSubtitles } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import type { SubtitleBackup } from '@/lib/types'

type Filter = 'all' | 'orphans'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

function formatRelativeAge(unixSeconds: number): string {
  const ageMs = Date.now() - unixSeconds * 1000
  const days = Math.floor(ageMs / 86_400_000)
  if (days === 0) return 'heute'
  if (days === 1) return 'gestern'
  if (days < 30) return `${days} Tage`
  const months = Math.floor(days / 30)
  return months === 1 ? '1 Monat' : `${months} Monate`
}

export function SubtitleBackupsPage() {
  const { t } = useTranslation('settings')
  const { data, isLoading, refetch } = useSubtitleBackups()
  const cleanupMutation = useCleanupSubtitleBackups()
  const [filter, setFilter] = useState<Filter>('all')
  const [busyPath, setBusyPath] = useState<string | null>(null)

  const backups = data?.backups ?? []
  const retentionDays = data?.retention_days ?? 0
  const orphanCount = data?.orphan_count ?? 0

  const visible = useMemo(
    () => (filter === 'orphans' ? backups.filter((b) => b.is_orphan) : backups),
    [backups, filter],
  )

  const totalBytes = useMemo(
    () => visible.reduce((sum, b) => sum + b.size_bytes, 0),
    [visible],
  )

  const handlePurgeOrphans = async () => {
    if (orphanCount === 0) return
    if (!confirm(`${orphanCount} verwaiste Backups löschen?`)) return
    cleanupMutation.mutate({ orphans_only: true, dry_run: false }, {
      onSuccess: () => void refetch(),
    })
  }

  const handlePurgeAged = async () => {
    if (retentionDays <= 0) {
      toast('Aufbewahrung ist deaktiviert (0 Tage)', 'error')
      return
    }
    if (!confirm(`Backups älter als ${retentionDays} Tage löschen?`)) return
    cleanupMutation.mutate(
      { older_than_days: retentionDays, orphans_only: false, dry_run: false },
      { onSuccess: () => void refetch() },
    )
  }

  const handleDryRun = async () => {
    cleanupMutation.mutate(
      { older_than_days: retentionDays, orphans_only: filter === 'orphans', dry_run: true },
      {
        onSuccess: (result) => {
          const n = result.deleted.length
          toast(`Trockenlauf: ${n} Backups würden gelöscht`, 'success')
        },
      },
    )
  }

  const handleRestore = async (backup: SubtitleBackup) => {
    if (!backup.restore_path) {
      toast('Kein Wiederherstellungs-Pfad verfügbar', 'error')
      return
    }
    setBusyPath(backup.path)
    try {
      await undoProcessSubtitle(backup.restore_path)
      toast('Backup wiederhergestellt', 'success')
      void refetch()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Wiederherstellen fehlgeschlagen', 'error')
    } finally {
      setBusyPath(null)
    }
  }

  const handleDelete = async (backup: SubtitleBackup) => {
    if (!confirm(`Backup endgültig löschen?\n${backup.path}`)) return
    setBusyPath(backup.path)
    try {
      await deleteSubtitles([backup.path])
      toast('Backup gelöscht', 'success')
      void refetch()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Löschen fehlgeschlagen', 'error')
    } finally {
      setBusyPath(null)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('subtitle_backups.title', 'Untertitel-Backups')}
        subtitle={t(
          'subtitle_backups.subtitle',
          'Backups (.bak.srt/.bak.ass) aus HI-Entfernung, Common-Fixes und Editor-Bearbeitungen',
        )}
      />

      <Link
        to="/settings/cleanup"
        className="inline-flex items-center gap-2 text-xs"
        style={{ color: 'var(--text-muted)' }}
      >
        <ArrowLeft size={13} />
        {t('subtitle_backups.back_to_cleanup', 'Zurück zur Bereinigung')}
      </Link>

      {/* Stats strip */}
      <div
        className="grid grid-cols-3 gap-4 px-5 py-4 rounded-xl"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div>
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {t('subtitle_backups.stat.total', 'Gesamt')}
          </div>
          <div className="text-2xl font-semibold tabular-nums" style={{ color: 'var(--text-primary)' }}>
            {backups.length}
          </div>
        </div>
        <div>
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {t('subtitle_backups.stat.orphans', 'Orphans')}
          </div>
          <div
            className="text-2xl font-semibold tabular-nums"
            style={{ color: orphanCount > 0 ? 'var(--warning)' : 'var(--text-primary)' }}
          >
            {orphanCount}
          </div>
        </div>
        <div>
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {t('subtitle_backups.stat.size', 'Speicher')}
          </div>
          <div className="text-2xl font-semibold tabular-nums" style={{ color: 'var(--text-primary)' }}>
            {formatBytes(totalBytes)}
          </div>
        </div>
      </div>

      {/* Bulk actions */}
      <div className="space-y-3">
        <div className="text-[10px] font-semibold uppercase tracking-wider px-1" style={{ color: 'var(--text-muted)' }}>
          {t('subtitle_backups.bulk.label', 'Bulk-Aktionen')}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={handlePurgeOrphans}
            disabled={orphanCount === 0 || cleanupMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-40"
            style={{ background: 'var(--warning)', color: '#000' }}
          >
            <AlertTriangle size={13} />
            {t('subtitle_backups.bulk.purge_orphans', 'Orphans löschen ({{count}})', { count: orphanCount })}
          </button>
          <button
            onClick={handlePurgeAged}
            disabled={retentionDays <= 0 || cleanupMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-40"
            style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          >
            <Trash2 size={13} />
            {retentionDays > 0
              ? t('subtitle_backups.bulk.purge_aged', 'Älter als {{days}}d löschen', { days: retentionDays })
              : t('subtitle_backups.bulk.retention_disabled', 'Aufbewahrung deaktiviert')}
          </button>
          <button
            onClick={handleDryRun}
            disabled={cleanupMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-40"
            style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          >
            <Eye size={13} />
            {t('subtitle_backups.bulk.dry_run', 'Trockenlauf')}
          </button>
        </div>
      </div>

      {/* Filter + List */}
      <div>
        <div className="flex items-center justify-between mb-3 px-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            {t('subtitle_backups.list.label', 'Backup-Liste')}
          </div>
          <div className="flex gap-1 text-xs">
            <button
              onClick={() => setFilter('all')}
              className="px-3 py-1 rounded"
              style={{
                background: filter === 'all' ? 'var(--accent-bg)' : 'transparent',
                color: filter === 'all' ? 'var(--accent)' : 'var(--text-muted)',
              }}
            >
              {t('subtitle_backups.filter.all', 'Alle')} ({backups.length})
            </button>
            <button
              onClick={() => setFilter('orphans')}
              className="px-3 py-1 rounded"
              style={{
                background: filter === 'orphans' ? 'var(--warning-bg, rgba(245,158,11,.13))' : 'transparent',
                color: filter === 'orphans' ? 'var(--warning)' : 'var(--text-muted)',
              }}
            >
              {t('subtitle_backups.filter.orphans', 'Orphans')} ({orphanCount})
            </button>
          </div>
        </div>

        {visible.length === 0 ? (
          <div
            className="text-sm text-center py-12 rounded-xl"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}
          >
            {filter === 'orphans'
              ? t('subtitle_backups.empty.orphans', 'Keine verwaisten Backups gefunden.')
              : t('subtitle_backups.empty.all', 'Keine Backups gefunden.')}
          </div>
        ) : (
          <div
            className="rounded-xl overflow-hidden"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <table className="w-full text-xs">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {[
                    t('subtitle_backups.column.language', 'Sprache'),
                    t('subtitle_backups.column.path', 'Pfad'),
                    t('subtitle_backups.column.size', 'Größe'),
                    t('subtitle_backups.column.age', 'Alter'),
                    t('subtitle_backups.column.status', 'Status'),
                    '',
                  ].map((h, i) => (
                    <th
                      key={i}
                      className="py-3 px-4 text-left font-medium"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((b) => (
                  <tr key={b.path} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="py-2 px-4">
                      <span
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase"
                        style={{ background: 'var(--accent-bg)', color: 'var(--accent)' }}
                      >
                        {b.language}
                        {b.modifiers.filter((m) => m !== 'bak').map((m) => (
                          <span key={m} style={{ color: 'var(--warning)' }}>{m}</span>
                        ))}
                      </span>
                    </td>
                    <td
                      className="py-2 px-4 truncate max-w-[400px]"
                      style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                      title={b.path}
                    >
                      {b.path.split(/[/\\]/).slice(-2).join('/')}
                    </td>
                    <td className="py-2 px-4 tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                      {formatBytes(b.size_bytes)}
                    </td>
                    <td className="py-2 px-4 tabular-nums" style={{ color: 'var(--text-muted)' }}>
                      {formatRelativeAge(b.modified_at)}
                    </td>
                    <td className="py-2 px-4">
                      {b.is_orphan ? (
                        <span
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium"
                          style={{ background: 'var(--warning-bg, rgba(245,158,11,.13))', color: 'var(--warning)' }}
                          title={t(
                            'subtitle_backups.tooltip.orphan',
                            'Weder aktiver Sub noch Video vorhanden',
                          )}
                        >
                          <AlertTriangle size={10} />
                          Orphan
                        </span>
                      ) : (
                        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>OK</span>
                      )}
                    </td>
                    <td className="py-2 px-4">
                      <div className="flex items-center justify-end gap-1">
                        {!b.is_orphan && (
                          <button
                            onClick={() => handleRestore(b)}
                            disabled={busyPath === b.path}
                            className="p-1.5 rounded hover:bg-zinc-800 disabled:opacity-40"
                            style={{ color: 'var(--accent)' }}
                            title={t('subtitle_backups.action.restore', 'Wiederherstellen')}
                          >
                            <RotateCcw size={13} />
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(b)}
                          disabled={busyPath === b.path}
                          className="p-1.5 rounded hover:bg-zinc-800 disabled:opacity-40"
                          style={{ color: 'var(--error)' }}
                          title={t('subtitle_backups.action.delete', 'Löschen')}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
