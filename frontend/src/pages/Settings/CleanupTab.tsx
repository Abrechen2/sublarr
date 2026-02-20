/**
 * CleanupTab -- Settings tab for subtitle cleanup management.
 *
 * Five sections:
 * 1. Disk Space Overview (DiskSpaceWidget + stats summary)
 * 2. Deduplication (scan + duplicate groups + batch delete)
 * 3. Orphaned Subtitles (scan + list + delete)
 * 4. Cleanup Rules (CRUD + run now)
 * 5. History (collapsible paginated table)
 */
import { useState, useCallback, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Search, Trash2, Loader2, Play, Plus, ChevronDown, ChevronRight,
  Power, PowerOff, Clock, History as HistoryIcon,
} from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import {
  useCleanupStats, useStartCleanupScan, useCleanupScanStatus,
  useDuplicates, useDeleteDuplicates,
  useOrphanedScan, useOrphanedFiles, useDeleteOrphaned,
  useCleanupRules, useCreateCleanupRule, useUpdateCleanupRule, useDeleteCleanupRule, useRunCleanupRule,
  useCleanupHistory, useCleanupPreview,
} from '@/hooks/useApi'
import { DiskSpaceWidget } from '@/components/cleanup/DiskSpaceWidget'
import { DedupGroupList } from '@/components/cleanup/DedupGroupList'
import { CleanupPreview } from '@/components/cleanup/CleanupPreview'
import type { CleanupRule, CleanupPreviewData } from '@/lib/types'

/** Format bytes into human-readable KB/MB/GB */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, i)
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

// ─── Section Wrapper ────────────────────────────────────────────────────────

function Section({ title, children, defaultOpen = true }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left"
        style={{ color: 'var(--text-primary)' }}
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <h3 className="text-sm font-semibold">{title}</h3>
      </button>
      {open && <div className="px-4 pb-4 space-y-4">{children}</div>}
    </div>
  )
}

// ─── Main CleanupTab ────────────────────────────────────────────────────────

export function CleanupTab() {
  const { t } = useTranslation('settings')

  // Data hooks
  const { data: stats, isLoading: statsLoading } = useCleanupStats()
  const startScan = useStartCleanupScan()
  const [isScanning, setIsScanning] = useState(false)
  const scanStatus = useCleanupScanStatus(isScanning)
  const { data: duplicatesData, refetch: refetchDuplicates } = useDuplicates()
  const deleteDuplicates = useDeleteDuplicates()
  const orphanedScan = useOrphanedScan()
  const { data: orphanedData, refetch: refetchOrphaned } = useOrphanedFiles()
  const deleteOrphaned = useDeleteOrphaned()
  const { data: rules } = useCleanupRules()
  const createRule = useCreateCleanupRule()
  const updateRule = useUpdateCleanupRule()
  const deleteRule = useDeleteCleanupRule()
  const runRule = useRunCleanupRule()
  const [historyPage, setHistoryPage] = useState(1)
  const { data: historyData } = useCleanupHistory(historyPage)
  const cleanupPreview = useCleanupPreview()

  // State
  const [previewData, setPreviewData] = useState<CleanupPreviewData | null>(null)
  const [pendingDeleteSelections, setPendingDeleteSelections] = useState<{ keep: string; delete: string[] }[] | null>(null)
  const [selectedOrphaned, setSelectedOrphaned] = useState<Set<string>>(new Set())
  const [showCreateRule, setShowCreateRule] = useState(false)
  const [newRule, setNewRule] = useState({ name: '', rule_type: 'dedup' as CleanupRule['rule_type'], enabled: true })

  // Stop polling when scan completes (polling via useCleanupScanStatus every 2s)
  useEffect(() => {
    if (scanStatus.data?.status === 'idle' && isScanning) {
      setIsScanning(false)
      void refetchDuplicates()
    }
  }, [scanStatus.data, isScanning, refetchDuplicates])

  // ─── Handlers ───────────────────────────────────────────────────────────

  const handleStartScan = useCallback(() => {
    startScan.mutate(undefined, {
      onSuccess: () => {
        setIsScanning(true)
        toast(t('cleanup.dedup.scanStarted', 'Duplicate scan started'))
      },
      onError: () => toast(t('cleanup.dedup.scanFailed', 'Failed to start scan'), 'error'),
    })
  }, [startScan, t])

  const handleDeleteDuplicates = useCallback((selections: { keep: string; delete: string[] }[]) => {
    setPendingDeleteSelections(selections)
    // Show preview
    cleanupPreview.mutate(undefined, {
      onSuccess: (data) => setPreviewData(data),
      onError: () => {
        // If preview fails, proceed with direct delete
        deleteDuplicates.mutate(selections, {
          onSuccess: (result) => {
            toast(`Deleted ${result.deleted} files, freed ${formatBytes(result.bytes_freed)}`)
            setPendingDeleteSelections(null)
          },
          onError: () => toast('Failed to delete duplicates', 'error'),
        })
      },
    })
  }, [cleanupPreview, deleteDuplicates])

  const handleConfirmDelete = useCallback(() => {
    if (!pendingDeleteSelections) return
    deleteDuplicates.mutate(pendingDeleteSelections, {
      onSuccess: (result) => {
        toast(`Deleted ${result.deleted} files, freed ${formatBytes(result.bytes_freed)}`)
        setPendingDeleteSelections(null)
        setPreviewData(null)
      },
      onError: () => toast('Failed to delete duplicates', 'error'),
    })
  }, [pendingDeleteSelections, deleteDuplicates])

  const handleOrphanedScan = useCallback(() => {
    orphanedScan.mutate(undefined, {
      onSuccess: () => {
        toast(t('cleanup.orphaned.scanStarted', 'Orphaned scan started'))
        void refetchOrphaned()
      },
      onError: () => toast(t('cleanup.orphaned.scanFailed', 'Failed to scan'), 'error'),
    })
  }, [orphanedScan, t, refetchOrphaned])

  const handleDeleteOrphaned = useCallback(() => {
    const paths = Array.from(selectedOrphaned)
    if (paths.length === 0) return
    deleteOrphaned.mutate(paths, {
      onSuccess: (result) => {
        toast(`Deleted ${result.deleted} orphaned files, freed ${formatBytes(result.bytes_freed)}`)
        setSelectedOrphaned(new Set())
      },
      onError: () => toast('Failed to delete orphaned files', 'error'),
    })
  }, [selectedOrphaned, deleteOrphaned])

  const handleCreateRule = useCallback(() => {
    if (!newRule.name.trim()) return
    createRule.mutate(
      { name: newRule.name, rule_type: newRule.rule_type, config_json: {}, enabled: newRule.enabled },
      {
        onSuccess: () => {
          toast(t('cleanup.rules.created', 'Rule created'))
          setShowCreateRule(false)
          setNewRule({ name: '', rule_type: 'dedup', enabled: true })
        },
        onError: () => toast('Failed to create rule', 'error'),
      }
    )
  }, [newRule, createRule, t])

  const handleToggleRule = useCallback((rule: CleanupRule) => {
    updateRule.mutate(
      { id: rule.id, data: { enabled: !rule.enabled } },
      { onError: () => toast('Failed to update rule', 'error') }
    )
  }, [updateRule])

  const handleDeleteRule = useCallback((id: number) => {
    deleteRule.mutate(id, {
      onSuccess: () => toast(t('cleanup.rules.deleted', 'Rule deleted')),
      onError: () => toast('Failed to delete rule', 'error'),
    })
  }, [deleteRule, t])

  const handleRunRule = useCallback((id: number) => {
    runRule.mutate(id, {
      onSuccess: () => toast(t('cleanup.rules.running', 'Rule execution started')),
      onError: () => toast('Failed to run rule', 'error'),
    })
  }, [runRule, t])

  // ─── Loading State ──────────────────────────────────────────────────────

  if (statsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  const scanProgress = scanStatus.data
  const groups = duplicatesData?.groups ?? []
  const orphanedFiles = orphanedData?.files ?? []
  const rulesList = rules ?? []
  const historyEntries = historyData?.entries ?? []

  return (
    <div className="space-y-5">
      {/* 1. Disk Space Overview */}
      <Section title={t('cleanup.diskSpace.title', 'Disk Space Analysis')}>
        {stats ? (
          <DiskSpaceWidget stats={stats} />
        ) : (
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>
            {t('cleanup.diskSpace.noData', 'Run a scan to see disk space analysis')}
          </div>
        )}
      </Section>

      {/* 2. Deduplication */}
      <Section title={t('cleanup.dedup.title', 'Deduplication')}>
        {/* Scan button + progress */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleStartScan}
            disabled={isScanning || startScan.isPending}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium text-white transition-opacity disabled:opacity-50"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {isScanning || startScan.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Search size={14} />
            )}
            {isScanning
              ? t('cleanup.dedup.scanning', 'Scanning...')
              : t('cleanup.dedup.scanButton', 'Scan for Duplicates')}
          </button>
          {isScanning && scanProgress && (
            <div className="flex-1">
              <div className="flex items-center justify-between text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
                <span>{t('cleanup.dedup.progress', 'Progress')}</span>
                <span>{scanProgress.progress} / {scanProgress.total}</span>
              </div>
              <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    backgroundColor: 'var(--accent)',
                    width: scanProgress.total > 0 ? `${(scanProgress.progress / scanProgress.total) * 100}%` : '0%',
                  }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Preview modal */}
        {previewData && (
          <CleanupPreview
            preview={previewData}
            onConfirm={handleConfirmDelete}
            onCancel={() => { setPreviewData(null); setPendingDeleteSelections(null) }}
            isConfirming={deleteDuplicates.isPending}
          />
        )}

        {/* Duplicate groups */}
        {!previewData && groups.length > 0 && (
          <DedupGroupList
            groups={groups}
            onDelete={handleDeleteDuplicates}
            isDeleting={deleteDuplicates.isPending}
          />
        )}

        {!previewData && !isScanning && groups.length === 0 && (
          <div className="text-sm py-4 text-center" style={{ color: 'var(--text-muted)' }}>
            {t('cleanup.dedup.noResults', 'No duplicates found. Run a scan to check.')}
          </div>
        )}
      </Section>

      {/* 3. Orphaned Subtitles */}
      <Section title={t('cleanup.orphaned.title', 'Orphaned Subtitles')}>
        <div className="flex items-center gap-3">
          <button
            onClick={handleOrphanedScan}
            disabled={orphanedScan.isPending}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium text-white transition-opacity disabled:opacity-50"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {orphanedScan.isPending ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            {t('cleanup.orphaned.scanButton', 'Scan for Orphaned')}
          </button>
          {selectedOrphaned.size > 0 && (
            <button
              onClick={handleDeleteOrphaned}
              disabled={deleteOrphaned.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white transition-opacity disabled:opacity-50"
              style={{ backgroundColor: 'var(--error)' }}
            >
              <Trash2 size={12} />
              {t('cleanup.orphaned.deleteSelected', 'Delete Selected')} ({selectedOrphaned.size})
            </button>
          )}
        </div>

        {orphanedFiles.length > 0 ? (
          <div className="space-y-1">
            {orphanedFiles.map((file) => (
              <label
                key={file.file_path}
                className="flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
              >
                <input
                  type="checkbox"
                  checked={selectedOrphaned.has(file.file_path)}
                  onChange={() => {
                    setSelectedOrphaned((prev) => {
                      const next = new Set(prev)
                      if (next.has(file.file_path)) {
                        next.delete(file.file_path)
                      } else {
                        next.add(file.file_path)
                      }
                      return next
                    })
                  }}
                  className="accent-[var(--accent)]"
                />
                <span
                  className="flex-1 text-xs truncate"
                  style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
                  title={file.file_path}
                >
                  {file.file_path}
                </span>
                <span
                  className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase shrink-0"
                  style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
                >
                  {file.format}
                </span>
                <span className="text-xs tabular-nums shrink-0" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                  {formatBytes(file.file_size)}
                </span>
              </label>
            ))}
          </div>
        ) : (
          <div className="text-sm py-4 text-center" style={{ color: 'var(--text-muted)' }}>
            {t('cleanup.orphaned.noResults', 'No orphaned subtitles found.')}
          </div>
        )}
      </Section>

      {/* 4. Cleanup Rules */}
      <Section title={t('cleanup.rules.title', 'Cleanup Rules')}>
        {/* Create rule button */}
        <div className="flex items-center justify-between">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {rulesList.length} {t('cleanup.rules.configured', 'rules configured')}
          </span>
          <button
            onClick={() => setShowCreateRule(!showCreateRule)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all"
            style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
          >
            <Plus size={12} />
            {t('cleanup.rules.create', 'Create Rule')}
          </button>
        </div>

        {/* Create form */}
        {showCreateRule && (
          <div
            className="rounded-lg p-3 space-y-3"
            style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--accent-dim)' }}
          >
            <input
              type="text"
              value={newRule.name}
              onChange={(e) => setNewRule((r) => ({ ...r, name: e.target.value }))}
              placeholder={t('cleanup.rules.namePlaceholder', 'Rule name')}
              className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
              style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            />
            <div className="flex items-center gap-3">
              <select
                value={newRule.rule_type}
                onChange={(e) => setNewRule((r) => ({ ...r, rule_type: e.target.value as CleanupRule['rule_type'] }))}
                className="px-3 py-2 rounded-md text-sm focus:outline-none"
                style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="dedup">{t('cleanup.rules.types.dedup', 'Deduplication')}</option>
                <option value="orphaned">{t('cleanup.rules.types.orphaned', 'Orphaned Files')}</option>
                <option value="old_backups">{t('cleanup.rules.types.old_backups', 'Old Backups')}</option>
              </select>
              <label className="flex items-center gap-1.5 text-xs cursor-pointer" style={{ color: 'var(--text-secondary)' }}>
                <input
                  type="checkbox"
                  checked={newRule.enabled}
                  onChange={(e) => setNewRule((r) => ({ ...r, enabled: e.target.checked }))}
                  className="accent-[var(--accent)]"
                />
                {t('cleanup.rules.enabled', 'Enabled')}
              </label>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCreateRule}
                disabled={createRule.isPending || !newRule.name.trim()}
                className="px-3 py-1.5 rounded text-xs font-medium text-white disabled:opacity-50"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {createRule.isPending ? <Loader2 size={12} className="animate-spin" /> : t('cleanup.rules.save', 'Save')}
              </button>
              <button
                onClick={() => setShowCreateRule(false)}
                className="px-3 py-1.5 rounded text-xs"
                style={{ color: 'var(--text-muted)' }}
              >
                {t('cleanup.rules.cancel', 'Cancel')}
              </button>
            </div>
          </div>
        )}

        {/* Rules list */}
        {rulesList.length > 0 ? (
          <div className="space-y-2">
            {rulesList.map((rule) => (
              <div
                key={rule.id}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
              >
                <button
                  onClick={() => handleToggleRule(rule)}
                  className="shrink-0"
                  title={rule.enabled ? t('cleanup.rules.disable', 'Disable') : t('cleanup.rules.enable', 'Enable')}
                >
                  {rule.enabled
                    ? <Power size={14} style={{ color: 'var(--success)' }} />
                    : <PowerOff size={14} style={{ color: 'var(--text-muted)' }} />}
                </button>

                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {rule.name}
                  </div>
                  <div className="flex items-center gap-2 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    <span
                      className="px-1.5 py-0.5 rounded uppercase font-medium"
                      style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
                    >
                      {rule.rule_type}
                    </span>
                    {rule.last_run_at && (
                      <span className="flex items-center gap-1">
                        <Clock size={10} />
                        {new Date(rule.last_run_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>

                <button
                  onClick={() => handleRunRule(rule.id)}
                  disabled={runRule.isPending}
                  className="shrink-0 flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-all"
                  style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
                  title={t('cleanup.rules.runNow', 'Run Now')}
                >
                  <Play size={10} />
                  {t('cleanup.rules.runNow', 'Run Now')}
                </button>

                <button
                  onClick={() => handleDeleteRule(rule.id)}
                  disabled={deleteRule.isPending}
                  className="shrink-0 p-1 rounded transition-colors"
                  style={{ color: 'var(--text-muted)' }}
                  title={t('cleanup.rules.delete', 'Delete')}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm py-4 text-center" style={{ color: 'var(--text-muted)' }}>
            {t('cleanup.rules.noRules', 'No cleanup rules configured. Create one to automate cleanup.')}
          </div>
        )}
      </Section>

      {/* 5. History (collapsible) */}
      <Section title={t('cleanup.history.title', 'Cleanup History')} defaultOpen={false}>
        {historyEntries.length > 0 ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    <th className="text-left py-2 px-2 font-medium" style={{ color: 'var(--text-muted)' }}>
                      {t('cleanup.history.date', 'Date')}
                    </th>
                    <th className="text-left py-2 px-2 font-medium" style={{ color: 'var(--text-muted)' }}>
                      {t('cleanup.history.action', 'Action')}
                    </th>
                    <th className="text-right py-2 px-2 font-medium" style={{ color: 'var(--text-muted)' }}>
                      {t('cleanup.history.processed', 'Processed')}
                    </th>
                    <th className="text-right py-2 px-2 font-medium" style={{ color: 'var(--text-muted)' }}>
                      {t('cleanup.history.deleted', 'Deleted')}
                    </th>
                    <th className="text-right py-2 px-2 font-medium" style={{ color: 'var(--text-muted)' }}>
                      {t('cleanup.history.freed', 'Freed')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {historyEntries.map((entry) => (
                    <tr key={entry.id} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td className="py-2 px-2" style={{ color: 'var(--text-secondary)' }}>
                        {new Date(entry.performed_at).toLocaleString()}
                      </td>
                      <td className="py-2 px-2">
                        <span
                          className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                          style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
                        >
                          {entry.action_type}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-right tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                        {entry.files_processed}
                      </td>
                      <td className="py-2 px-2 text-right tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}>
                        {entry.files_deleted}
                      </td>
                      <td className="py-2 px-2 text-right tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>
                        {formatBytes(entry.bytes_freed)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* Pagination */}
            {historyData && historyData.total > 50 && (
              <div className="flex items-center justify-center gap-2 pt-2">
                <button
                  onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
                  disabled={historyPage <= 1}
                  className="px-2 py-1 rounded text-xs disabled:opacity-40"
                  style={{ color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
                >
                  {t('cleanup.history.prev', 'Previous')}
                </button>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {historyPage} / {Math.ceil(historyData.total / 50)}
                </span>
                <button
                  onClick={() => setHistoryPage((p) => p + 1)}
                  disabled={historyPage >= Math.ceil(historyData.total / 50)}
                  className="px-2 py-1 rounded text-xs disabled:opacity-40"
                  style={{ color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
                >
                  {t('cleanup.history.next', 'Next')}
                </button>
              </div>
            )}
          </>
        ) : (
          <div className="flex items-center justify-center gap-2 py-6 text-sm" style={{ color: 'var(--text-muted)' }}>
            <HistoryIcon size={16} />
            {t('cleanup.history.empty', 'No cleanup history yet')}
          </div>
        )}
      </Section>
    </div>
  )
}
