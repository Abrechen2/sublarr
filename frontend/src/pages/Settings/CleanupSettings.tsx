/**
 * CleanupSettings — simplified cleanup management page.
 *
 * Five fixed cleanup operations (no create/delete). Each is an expandable
 * card with a toggle, inline config, schedule picker, preview, and run action.
 * Deduplication is a separate section below.
 */
import { useState, useCallback, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Globe, ArrowUpCircle, FileX, Database, Archive, Layers, FileWarning, ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { DiskSpaceWidget } from '@/components/cleanup/DiskSpaceWidget'
import { CleanupOpCard, type OpMeta } from '@/components/cleanup/CleanupOpCard'
import { DedupGroupList } from '@/components/cleanup/DedupGroupList'
import { CleanupPreview } from '@/components/cleanup/CleanupPreview'
import { toast } from '@/components/shared/Toast'
import {
  useCleanupRules,
  useCreateCleanupRule,
  useUpdateCleanupRule,
  useCleanupStats,
  useStartCleanupScan,
  useCleanupScanStatus,
  useDuplicates,
  useDeleteDuplicates,
  useCleanupHistory,
  useCleanupPreview,
  useConfig,
  useUpdateConfig,
} from '@/hooks/useSystemApi'
import type { CleanupRule, CleanupPreviewData } from '@/lib/types'
import { strVal } from '@/lib/configUtils'

// ─── Fixed operation definitions ─────────────────────────────────────────────

const OPERATIONS: OpMeta[] = [
  {
    ruleType: 'language_filter',
    Icon: Globe,
    iconColor: 'var(--accent)',
    iconBg: 'rgba(34,211,238,.13)',
    title: 'Sprachen-Filter',
    description: 'Löscht Subtitle-Sidecars in Sprachen, die nicht in der Behalten-Liste stehen',
    defaultName: 'Sprachen-Filter',
  },
  {
    ruleType: 'format_upgrade',
    Icon: ArrowUpCircle,
    iconColor: 'var(--warning)',
    iconBg: 'rgba(245,158,11,.12)',
    title: 'Format-Upgrade',
    description: 'Löscht SRT-Dateien, wenn eine ASS-Version für dieselbe Episode vorhanden ist',
    defaultName: 'Format-Upgrade',
  },
  {
    ruleType: 'orphan_files',
    Icon: FileX,
    iconColor: 'var(--error)',
    iconBg: 'rgba(239,68,68,.11)',
    title: 'Verwaiste Dateien',
    description: 'Löscht Subtitle-Sidecars ohne zugehörige Videodatei im selben Ordner',
    defaultName: 'Verwaiste Dateien',
  },
  {
    ruleType: 'orphan_db',
    Icon: Database,
    iconColor: '#6b9df0',
    iconBg: 'rgba(107,157,240,.12)',
    title: 'Verwaiste DB-Einträge',
    description: 'Entfernt Datenbankeinträge, deren Datei auf der Festplatte fehlt',
    defaultName: 'Verwaiste DB-Einträge',
  },
  {
    ruleType: 'old_backups',
    Icon: Archive,
    iconColor: 'var(--text-secondary)',
    iconBg: 'rgba(155,161,168,.1)',
    title: 'Alte Backups',
    description: 'Löscht Remux-Backup-Dateien nach Ablauf der Aufbewahrungsfrist',
    defaultName: 'Alte Backups',
  },
  {
    ruleType: 'old_subtitle_baks',
    Icon: FileWarning,
    iconColor: 'var(--warning, #f59e0b)',
    iconBg: 'rgba(245,158,11,.12)',
    title: 'Alte Untertitel-Backups (.bak)',
    description:
      'Verwaiste .bak.srt/.bak.ass werden sofort entfernt; übrige nach Aufbewahrungsfrist (0 = nie)',
    defaultName: 'Alte Untertitel-Backups',
  },
  {
    ruleType: 'foreign_tracks',
    Icon: Layers,
    iconColor: 'var(--accent)',
    iconBg: 'rgba(34,211,238,.13)',
    title: 'Fremdsprachen-Tracks entfernen',
    description:
      'Entfernt eingebettete Untertitel-Spuren aus den Videos, deren Sprache nicht in der Behalten-Liste steht (Original landet als Backup im Papierkorb)',
    defaultName: 'Fremdsprachen-Tracks entfernen',
    defaultConfig: { keep_languages: ['de', 'en'], keep_und: true },
  },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

// ─── History section ──────────────────────────────────────────────────────────

function HistorySection() {
  const { t } = useTranslation('settings')
  const [page, setPage] = useState(1)
  const { data: historyData } = useCleanupHistory(page)
  const entries = historyData?.entries ?? []
  const total = historyData?.total ?? 0

  if (entries.length === 0) return null

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div className="px-5 py-4" style={{ borderBottom: '1px solid var(--border)' }}>
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('cleanup.history.title', 'Cleanup History')}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {[
                t('cleanup.history.date'),
                t('cleanup.history.action'),
                t('cleanup.history.processed'),
                t('cleanup.history.deleted'),
                t('cleanup.history.freed'),
              ].map((h) => (
                <th
                  key={h}
                  className="py-3 px-4 text-left font-medium"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id} style={{ borderBottom: '1px solid var(--border)' }}>
                <td className="py-3 px-4" style={{ color: 'var(--text-secondary)' }}>
                  {new Date(entry.performed_at).toLocaleString('de-DE')}
                </td>
                <td className="py-3 px-4">
                  <span
                    className="px-2 py-0.5 rounded text-[10px] font-medium"
                    style={{ background: 'var(--accent-bg)', color: 'var(--accent)' }}
                  >
                    {entry.action_type}
                  </span>
                </td>
                <td
                  className="py-3 px-4 tabular-nums"
                  style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
                >
                  {entry.files_processed}
                </td>
                <td
                  className="py-3 px-4 tabular-nums"
                  style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}
                >
                  {entry.files_deleted}
                </td>
                <td
                  className="py-3 px-4 tabular-nums"
                  style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}
                >
                  {formatBytes(entry.bytes_freed)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {total > 50 && (
        <div className="flex items-center justify-center gap-3 p-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-3 py-1.5 rounded text-xs disabled:opacity-40"
            style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
          >
            {t('cleanup.history.prev')}
          </button>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {page} / {Math.ceil(total / 50)}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={page >= Math.ceil(total / 50)}
            className="px-3 py-1.5 rounded text-xs disabled:opacity-40"
            style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
          >
            {t('cleanup.history.next')}
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function CleanupSettings() {
  const { t } = useTranslation('settings')
  const { data: rules = [], isLoading } = useCleanupRules()
  const { data: stats } = useCleanupStats()
  const createRule = useCreateCleanupRule()
  const updateRule = useUpdateCleanupRule()
  const { data: config } = useConfig()
  const { mutate: updateConfig, isPending: isUpdatingConfig } = useUpdateConfig()

  // Dedup state
  const startScan = useStartCleanupScan()
  const [isScanning, setIsScanning] = useState(false)
  const scanStatus = useCleanupScanStatus(isScanning)
  const { data: duplicatesData, refetch: refetchDuplicates } = useDuplicates()
  const deleteDuplicates = useDeleteDuplicates()
  const cleanupPreview = useCleanupPreview()
  const [dedupPreviewData, setDedupPreviewData] = useState<CleanupPreviewData | null>(null)
  const [pendingDeleteSelections, setPendingDeleteSelections] = useState<
    { keep: string; delete: string[] }[] | null
  >(null)

  // Stop scan polling when complete
  useEffect(() => {
    if (scanStatus.data?.status === 'idle' && isScanning) {
      setIsScanning(false)
      void refetchDuplicates()
    }
  }, [scanStatus.data, isScanning, refetchDuplicates])

  // ── Operation handlers ──────────────────────────────────────────────────────

  const handleToggle = useCallback(
    (ruleType: string, enabled: boolean) => {
      const existing = rules.find((r: CleanupRule) => r.rule_type === ruleType)
      const meta = OPERATIONS.find((op) => op.ruleType === ruleType)!

      if (existing) {
        updateRule.mutate(
          { id: existing.id, data: { enabled } },
          { onError: () => toast(t('cleanup.errors.save_failed'), 'error') },
        )
      } else {
        createRule.mutate(
          {
            name: meta.defaultName,
            rule_type: ruleType as CleanupRule['rule_type'],
            config_json: meta.defaultConfig ?? {},
            enabled,
            schedule: 'manual',
          },
          { onError: () => toast(t('cleanup.errors.create_failed'), 'error') },
        )
      }
    },
    [rules, createRule, updateRule, t],
  )

  const handleUpdate = useCallback(
    (ruleType: string, patch: Partial<CleanupRule>) => {
      const existing = rules.find((r: CleanupRule) => r.rule_type === ruleType)
      if (!existing) return
      updateRule.mutate(
        { id: existing.id, data: patch },
        { onError: () => toast(t('cleanup.errors.save_failed'), 'error') },
      )
    },
    [rules, updateRule, t],
  )

  // ── Dedup handlers ──────────────────────────────────────────────────────────

  const handleStartScan = useCallback(() => {
    startScan.mutate(undefined, {
      onSuccess: () => setIsScanning(true),
      onError: () => toast(t('cleanup.errors.scan_failed'), 'error'),
    })
  }, [startScan, t])

  const handleDeleteDuplicates = useCallback(
    (selections: { keep: string; delete: string[] }[]) => {
      setPendingDeleteSelections(selections)
      cleanupPreview.mutate(undefined, {
        onSuccess: (data: CleanupPreviewData) => setDedupPreviewData(data),
        onError: () => {
          deleteDuplicates.mutate(selections, {
            onSuccess: (result: { deleted: number; bytes_freed: number }) => {
              toast(t('cleanup.dedup.deleted_files', { count: result.deleted, size: formatBytes(result.bytes_freed) }))
              setPendingDeleteSelections(null)
            },
            onError: () => toast(t('cleanup.errors.delete_failed'), 'error'),
          })
        },
      })
    },
    [cleanupPreview, deleteDuplicates, t],
  )

  const handleConfirmDedupDelete = useCallback(() => {
    if (!pendingDeleteSelections) return
    deleteDuplicates.mutate(pendingDeleteSelections, {
      onSuccess: (result: { deleted: number; bytes_freed: number }) => {
        toast(t('cleanup.dedup.deleted_files', { count: result.deleted, size: formatBytes(result.bytes_freed) }))
        setPendingDeleteSelections(null)
        setDedupPreviewData(null)
      },
      onError: () => toast(t('cleanup.errors.delete_failed'), 'error'),
    })
  }, [pendingDeleteSelections, deleteDuplicates, t])

  // ── Render ──────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  const groups = duplicatesData?.groups ?? []

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('cleanup.page.title', 'Bereinigung')}
        subtitle={t(
          'cleanup.page.subtitle',
          'Automatisierte Bereinigung von Sidecar-Dateien und Datenbankeinträgen',
        )}
      />

      {/* Disk stats */}
      {stats && stats.total_files > 0 && <DiskSpaceWidget stats={stats} />}

      {/* ── Automatic cleanup operations ── */}
      <div>
        <div
          className="text-[10px] font-semibold uppercase tracking-wider mb-3 px-1"
          style={{ color: 'var(--text-muted)' }}
        >
          {t('cleanup.auto_cleanup_heading')}
        </div>
        <div className="space-y-3">
          {OPERATIONS.map((op) => {
            const rule = rules.find((r: CleanupRule) => r.rule_type === op.ruleType) ?? null
            return (
              <CleanupOpCard
                key={op.ruleType}
                meta={op}
                rule={rule}
                onToggle={(enabled) => handleToggle(op.ruleType, enabled)}
                onUpdate={(patch) => handleUpdate(op.ruleType, patch)}
              />
            )
          })}
        </div>
      </div>

      {/* ── Signs removal level ── */}
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-wider mb-3 px-1 text-muted">
          {t('cleanup.signs_removal.label')}
        </div>
        <div className="rounded-xl bg-surface border border-border px-5 py-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-primary">
                {t('cleanup.signs_removal.label')}
              </div>
              <div className="text-xs mt-0.5 text-muted">
                {t('cleanup.signs_removal.hint')}
              </div>
            </div>
            <select
              id="cleanup-signs-removal-level"
              data-testid="select-signs-removal-level"
              className="bg-elevated border border-border text-primary rounded text-sm px-3 py-2 min-w-[200px]"
              value={strVal(config, 'cleanup_signs_removal_level', 'off')}
              onChange={(e) => updateConfig({ cleanup_signs_removal_level: e.target.value })}
              disabled={isUpdatingConfig}
            >
              <option value="off">{t('cleanup.signs_removal.off')}</option>
              <option value="signs">{t('cleanup.signs_removal.signs')}</option>
              <option value="signs_forced">{t('cleanup.signs_removal.signs_forced')}</option>
              <option value="signs_forced_songs">{t('cleanup.signs_removal.signs_forced_songs')}</option>
            </select>
          </div>
        </div>
      </div>

      {/* ── Deduplication ── */}
      <div>
        <div
          className="text-[10px] font-semibold uppercase tracking-wider mb-3 px-1"
          style={{ color: 'var(--text-muted)' }}
        >
          {t('cleanup.dedup_heading')}
        </div>
        <div
          className="rounded-xl overflow-hidden"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          {/* Dedup header */}
          <div
            className="flex items-center gap-4 px-5 py-4"
            style={{ borderBottom: '1px solid var(--border)' }}
          >
            <div
              className="flex items-center justify-center rounded-xl flex-shrink-0"
              style={{ width: 40, height: 40, background: 'rgba(167,139,250,.12)' }}
            >
              <Layers size={18} style={{ color: '#a78bfa' }} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                {t('cleanup.dedup.scanner_title')}
              </div>
              <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                {t('cleanup.dedup.scanner_desc')}
              </div>
            </div>
            <button
              onClick={handleStartScan}
              disabled={isScanning || startScan.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 flex-shrink-0"
              style={{ background: 'var(--accent)', color: '#000' }}
            >
              {isScanning ? <Loader2 size={13} className="animate-spin" /> : <Layers size={13} />}
              {isScanning ? t('cleanup.dedup.scanning_short') : t('cleanup.dedup.scanButton', 'Neu scannen')}
            </button>
          </div>

          {/* Dedup body */}
          <div className="p-5">
            {dedupPreviewData ? (
              <CleanupPreview
                preview={dedupPreviewData}
                onConfirm={handleConfirmDedupDelete}
                onCancel={() => {
                  setDedupPreviewData(null)
                  setPendingDeleteSelections(null)
                }}
                isConfirming={deleteDuplicates.isPending}
              />
            ) : groups.length > 0 ? (
              <DedupGroupList
                groups={groups}
                totalGroups={duplicatesData?.total}
                onDelete={handleDeleteDuplicates}
                isDeleting={deleteDuplicates.isPending}
              />
            ) : (
              <div
                className="text-sm text-center py-6"
                style={{ color: 'var(--text-muted)' }}
              >
                {t('cleanup.dedup.noResults', 'Keine Duplikate gefunden. Scan starten um zu prüfen.')}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── History ── */}
      <HistorySection />

      {/* ── Footer: Manual tools ── */}
      <div
        className="rounded-xl px-5 py-4 flex items-center justify-between"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div>
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {t('cleanup.footer.subtitle_backups.title', 'Untertitel-Backup-Verwaltung')}
          </div>
          <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {t(
              'cleanup.footer.subtitle_backups.description',
              'Manuelle Übersicht aller .bak-Dateien — Wiederherstellen, Orphans löschen, Trockenlauf.',
            )}
          </div>
        </div>
        <Link
          to="/settings/cleanup/subtitle-backups"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium flex-shrink-0"
          style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
        >
          {t('cleanup.footer.subtitle_backups.open', 'Öffnen')}
          <ArrowRight size={13} />
        </Link>
      </div>
    </div>
  )
}
