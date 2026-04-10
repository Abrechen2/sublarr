import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash2, RotateCcw, X, FileVideo, Files, AlertTriangle, Loader2 } from 'lucide-react'
import {
  useTrashOverview,
  useRestoreSidecarBatch,
  useDeleteSidecarBatch,
  useDeleteMkvBackup,
  useRestoreMkvBackup,
} from '@/hooks/useTrashApi'
import { PageHeader } from '@/components/layout/PageHeader'
import { formatBytes } from '@/lib/diskUtils'
import type { SidecarBatch, MkvBackup } from '@/api/trash'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return iso
  }
}

function daysUntil(iso: string | null): number | null {
  if (!iso) return null
  try {
    const diff = new Date(iso).getTime() - Date.now()
    return Math.ceil(diff / 86_400_000)
  } catch {
    return null
  }
}

// ─── Expiry Badge ─────────────────────────────────────────────────────────────

function ExpiryBadge({ expiresAt }: { expiresAt: string | null }) {
  const { t } = useTranslation('common')
  const days = daysUntil(expiresAt)
  if (days === null) return null

  const urgent = days <= 3
  const color = days <= 0 ? 'var(--error)' : urgent ? 'var(--warning)' : 'var(--text-tertiary)'
  const label =
    days <= 0
      ? t('trash.expires_today')
      : t('trash.expires_in_days', { count: days })

  return (
    <span style={{ fontSize: '11px', color }}>{label}</span>
  )
}

// ─── Stats Bar ────────────────────────────────────────────────────────────────

interface StatsBarProps {
  sidecarCount: number
  mkvCount: number
  totalSize: number
  retentionSubtitle: number
  retentionMkv: number
}

function StatsBar({ sidecarCount, mkvCount, totalSize, retentionSubtitle, retentionMkv }: StatsBarProps) {
  const { t } = useTranslation('common')

  const stats = [
    {
      label: t('trash.subtitle_sidecars'),
      value: sidecarCount,
      sub: t('trash.retention_subtitle', { days: retentionSubtitle }),
      icon: <Files size={14} style={{ color: 'var(--accent)' }} />,
    },
    {
      label: t('trash.video_backups'),
      value: mkvCount,
      sub: t('trash.retention_mkv', { days: retentionMkv }),
      icon: <FileVideo size={14} style={{ color: 'var(--accent)' }} />,
    },
    {
      label: t('trash.total_size', { size: '' }).trim(),
      value: formatBytes(totalSize),
      sub: null,
      icon: <Trash2 size={14} style={{ color: 'var(--text-muted)' }} />,
    },
  ]

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '1px',
        background: 'var(--border)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
      }}
    >
      {stats.map((s) => (
        <div
          key={s.label}
          style={{
            padding: '14px 18px',
            background: 'var(--bg-surface)',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          {s.icon}
          <div>
            <div style={{ fontSize: '20px', fontWeight: 700, fontFamily: 'var(--font-mono)', lineHeight: 1 }}>
              {s.value}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '3px' }}>{s.label}</div>
            {s.sub && (
              <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '1px' }}>{s.sub}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── MKV Restore Modal ────────────────────────────────────────────────────────

interface MkvRestoreModalProps {
  backup: MkvBackup
  onClose: () => void
}

function MkvRestoreModal({ backup, onClose }: MkvRestoreModalProps) {
  const { t } = useTranslation('common')
  const [deleteSidecars, setDeleteSidecars] = useState(false)
  const restore = useRestoreMkvBackup()

  const handleRestore = () => {
    if (!backup.video_path) return
    restore.mutate(
      { backupPath: backup.path, videoPath: backup.video_path, deleteSidecars },
      { onSuccess: onClose },
    )
  }

  const filename = backup.path.split(/[/\\]/).pop() ?? backup.path

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        className="rounded-xl p-6 w-[480px] space-y-4"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">{t('trash.mkv_restore_title')}</h2>
          <button onClick={onClose} style={{ color: 'var(--text-secondary)' }}>
            <X size={18} />
          </button>
        </div>

        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          {t('trash.mkv_restore_desc')}
        </p>

        <div
          className="rounded-lg p-3 text-xs space-y-1"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
        >
          <div className="font-medium truncate">{filename}</div>
          {backup.video_path && (
            <div style={{ color: 'var(--text-secondary)' }} className="truncate">
              → {backup.video_path}
            </div>
          )}
          <div style={{ color: 'var(--text-tertiary)' }}>{formatBytes(backup.size_bytes)}</div>
        </div>

        {!backup.video_path && (
          <div
            className="flex items-center gap-2 rounded-lg p-3 text-xs"
            style={{
              background: 'color-mix(in srgb, var(--warning) 12%, transparent)',
              color: 'var(--warning)',
            }}
          >
            <AlertTriangle size={14} />
            {t('trash.mkv_no_video')}
          </div>
        )}

        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={deleteSidecars}
            onChange={(e) => setDeleteSidecars(e.target.checked)}
            className="rounded"
          />
          <span className="text-sm">{t('trash.delete_sidecars_label')}</span>
        </label>

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm"
            style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          >
            {t('trash.cancel')}
          </button>
          <button
            onClick={handleRestore}
            disabled={!backup.video_path || restore.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            {restore.isPending ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
            {t('trash.restore')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Sidecar Batch Card ───────────────────────────────────────────────────────

function SidecarBatchCard({ batch }: { batch: SidecarBatch }) {
  const { t } = useTranslation('common')
  const [expanded, setExpanded] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const restore = useRestoreSidecarBatch()
  const remove = useDeleteSidecarBatch()

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="font-medium text-sm truncate">
            {batch.series_name || t('trash.unknown_series')}
            {batch.language && (
              <span
                className="ml-2 text-xs px-1.5 py-0.5 rounded"
                style={{ background: 'var(--accent-muted)', color: 'var(--accent)' }}
              >
                {batch.language}
              </span>
            )}
          </div>
          <div className="text-xs mt-0.5 flex items-center gap-2 flex-wrap" style={{ color: 'var(--text-secondary)' }}>
            <span>
              {batch.file_count} {batch.file_count === 1 ? t('trash.file_singular') : t('trash.file_plural')}
            </span>
            <span>·</span>
            <span>{formatBytes(batch.size_bytes)}</span>
            <span>·</span>
            <span>{t('trash.deleted_on')} {formatDate(batch.created_at)}</span>
          </div>
          {batch.expires_at && (
            <div className="mt-1">
              <ExpiryBadge expiresAt={batch.expires_at} />
            </div>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => restore.mutate(batch.batch_id)}
            disabled={restore.isPending}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-medium"
            style={{ background: 'var(--accent-muted)', color: 'var(--accent)' }}
            title={t('trash.restore_btn')}
          >
            {restore.isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <RotateCcw size={12} />
            )}
            {t('trash.restore_btn')}
          </button>

          {confirmDelete ? (
            <>
              <button
                onClick={() => remove.mutate(batch.batch_id)}
                disabled={remove.isPending}
                className="px-2.5 py-1.5 rounded-md text-xs font-medium text-white"
                style={{ background: 'var(--error)' }}
              >
                {remove.isPending ? <Loader2 size={12} className="animate-spin" /> : t('trash.delete_btn')}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="px-2 py-1.5 rounded-md text-xs"
                style={{ color: 'var(--text-secondary)' }}
              >
                ✕
              </button>
            </>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="p-1.5 rounded-md"
              style={{ color: 'var(--text-tertiary)' }}
              title={t('trash.delete_confirm')}
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {batch.files.length > 0 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="text-xs"
          style={{ color: 'var(--text-tertiary)' }}
        >
          {expanded ? t('trash.hide_files') : t('trash.show_files', { count: batch.files.length })}
        </button>
      )}

      {expanded && (
        <ul className="space-y-0.5">
          {batch.files.map((f) => (
            <li key={f} className="text-xs truncate" style={{ color: 'var(--text-secondary)' }}>
              {f.split(/[/\\]/).pop() ?? f}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ─── MKV Backup Card ──────────────────────────────────────────────────────────

function MkvBackupCard({ backup }: { backup: MkvBackup }) {
  const { t } = useTranslation('common')
  const [showModal, setShowModal] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const remove = useDeleteMkvBackup()
  const filename = backup.path.split(/[/\\]/).pop() ?? backup.path

  return (
    <>
      <div
        className="rounded-lg p-4"
        style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="font-medium text-sm truncate">{filename}</div>
            <div className="text-xs mt-0.5 flex items-center gap-2 flex-wrap" style={{ color: 'var(--text-secondary)' }}>
              <span>{formatBytes(backup.size_bytes)}</span>
              {backup.expires_at && (
                <>
                  <span>·</span>
                  <ExpiryBadge expiresAt={backup.expires_at} />
                </>
              )}
            </div>
            {backup.video_path ? (
              <div className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-tertiary)' }}>
                {backup.video_path}
              </div>
            ) : (
              <div className="flex items-center gap-1 text-xs mt-0.5" style={{ color: 'var(--warning)' }}>
                <AlertTriangle size={11} />
                {t('trash.original_not_found')}
              </div>
            )}
          </div>

          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => setShowModal(true)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium"
              style={{ background: 'var(--accent-muted)', color: 'var(--accent)' }}
            >
              <RotateCcw size={12} />
              {t('trash.restore')}
            </button>

            {confirmDelete ? (
              <>
                <button
                  onClick={() => remove.mutate(backup.path)}
                  disabled={remove.isPending}
                  className="px-2.5 py-1.5 rounded-md text-xs font-medium text-white"
                  style={{ background: 'var(--error)' }}
                >
                  {remove.isPending ? <Loader2 size={12} className="animate-spin" /> : t('trash.delete_btn')}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="px-2 py-1.5 rounded-md text-xs"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  ✕
                </button>
              </>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                className="p-1.5 rounded-md"
                style={{ color: 'var(--text-tertiary)' }}
                title={t('trash.delete_confirm')}
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        </div>
      </div>

      {showModal && <MkvRestoreModal backup={backup} onClose={() => setShowModal(false)} />}
    </>
  )
}

// ─── Section Header ───────────────────────────────────────────────────────────

interface SectionHeaderProps {
  icon: React.ReactNode
  title: string
  count: number
  retention: string
}

function SectionHeader({ icon, title, count, retention }: SectionHeaderProps) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        {icon}
        <h2 className="text-sm font-semibold">{title}</h2>
        <span
          className="text-xs px-1.5 py-0.5 rounded-full font-medium"
          style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
        >
          {count}
        </span>
      </div>
      <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>{retention}</span>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function TrashPage() {
  const { t } = useTranslation('common')
  const { data, isLoading } = useTrashOverview()

  const sidecarCount = data?.sidecar_batches.length ?? 0
  const mkvCount = data?.mkv_backups.length ?? 0
  const totalSize = data?.total_size_bytes ?? 0
  const retentionSubtitle = data?.retention.subtitle_trash_days ?? 30
  const retentionMkv = data?.retention.mkv_backup_days ?? 7

  return (
    <div className="space-y-6">
      <PageHeader title={t('trash.page_title')} />

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin" style={{ color: 'var(--accent)' }} />
        </div>
      ) : sidecarCount === 0 && mkvCount === 0 ? (
        <div
          className="rounded-xl p-12 text-center"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
        >
          <Trash2 size={36} className="mx-auto mb-3" style={{ color: 'var(--text-tertiary)' }} />
          <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>
            {t('trash.empty')}
          </p>
        </div>
      ) : (
        <>
          <StatsBar
            sidecarCount={sidecarCount}
            mkvCount={mkvCount}
            totalSize={totalSize}
            retentionSubtitle={retentionSubtitle}
            retentionMkv={retentionMkv}
          />

          {sidecarCount > 0 && (
            <section className="space-y-3">
              <SectionHeader
                icon={<Files size={15} style={{ color: 'var(--accent)' }} />}
                title={t('trash.subtitle_sidecars')}
                count={sidecarCount}
                retention={t('trash.retention_subtitle', { days: retentionSubtitle })}
              />
              <div className="space-y-2">
                {data!.sidecar_batches.map((batch) => (
                  <SidecarBatchCard key={batch.batch_id} batch={batch} />
                ))}
              </div>
            </section>
          )}

          {mkvCount > 0 && (
            <section className="space-y-3">
              <SectionHeader
                icon={<FileVideo size={15} style={{ color: 'var(--accent)' }} />}
                title={t('trash.video_backups')}
                count={mkvCount}
                retention={t('trash.retention_mkv', { days: retentionMkv })}
              />
              <div className="space-y-2">
                {data!.mkv_backups.map((bak) => (
                  <MkvBackupCard key={bak.path} backup={bak} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
