/**
 * CleanupSettings — dedicated Settings page for subtitle cleanup rule management.
 *
 * Layout:
 *   Left sidebar (260px): rule list + new rule button (RuleSidebar)
 *   Right main: disk space widget, rule detail, dedup section, history
 */
import { useState, useCallback, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { RuleSidebar } from '@/components/cleanup/RuleSidebar'
import { RuleDetail } from '@/components/cleanup/RuleDetail'
import { DiskSpaceWidget } from '@/components/cleanup/DiskSpaceWidget'
import { DedupGroupList } from '@/components/cleanup/DedupGroupList'
import { CleanupPreview } from '@/components/cleanup/CleanupPreview'
import { toast } from '@/components/shared/Toast'
import {
  useCleanupRules, useCreateCleanupRule, useUpdateCleanupRule,
  useDeleteCleanupRule, useRunCleanupRule, useRulePreview,
  useCleanupStats, useStartCleanupScan, useCleanupScanStatus,
  useDuplicates, useDeleteDuplicates,
  useCleanupHistory, useCleanupPreview,
} from '@/hooks/useSystemApi'
import type { CleanupRule, CleanupPreviewData } from '@/lib/types'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

// ─── Rule Type Options (for new rule modal) ──────────────────────────────────

const RULE_TYPES = [
  { value: 'language_filter', label: 'Sprach-Filter', desc: 'Löscht Sidecars in nicht erlaubten Sprachen' },
  { value: 'format_upgrade', label: 'Format-Upgrade', desc: 'Löscht SRT wenn ASS für gleiche Episode existiert' },
  { value: 'orphan_files', label: 'Verwaiste Dateien', desc: 'Löscht Subtitle-Sidecars ohne Video auf Disk' },
  { value: 'orphan_db', label: 'DB-Bereinigung', desc: 'Entfernt DB-Einträge ohne Datei auf Disk' },
]

// ─── New Rule Modal ──────────────────────────────────────────────────────────

function NewRuleModal({
  onClose,
  onCreate,
}: {
  onClose: () => void
  onCreate: (name: string, ruleType: string) => void
}) {
  const [name, setName] = useState('')
  const [ruleType, setRuleType] = useState('language_filter')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        className="rounded-xl p-6 w-96 space-y-4"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          Neue Cleanup-Regel
        </h3>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Regelname"
          className="w-full px-3 py-2 rounded-lg text-sm focus:outline-none"
          style={{
            background: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
          }}
        />
        <div className="space-y-2">
          {RULE_TYPES.map((rt) => (
            <label
              key={rt.value}
              className="flex items-start gap-3 p-3 rounded-lg cursor-pointer"
              style={{
                background: ruleType === rt.value ? 'var(--accent-bg)' : 'var(--bg-primary)',
                border: `1px solid ${ruleType === rt.value ? 'var(--accent)' : 'var(--border)'}`,
              }}
            >
              <input
                type="radio"
                name="ruleType"
                value={rt.value}
                checked={ruleType === rt.value}
                onChange={() => setRuleType(rt.value)}
                className="mt-0.5"
              />
              <div>
                <div className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {rt.label}
                </div>
                <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                  {rt.desc}
                </div>
              </div>
            </label>
          ))}
        </div>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded text-xs"
            style={{ color: 'var(--text-muted)' }}
          >
            Abbrechen
          </button>
          <button
            onClick={() => {
              if (name.trim()) onCreate(name.trim(), ruleType)
            }}
            disabled={!name.trim()}
            className="px-4 py-1.5 rounded text-xs font-medium text-white disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            Erstellen
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── History Section ─────────────────────────────────────────────────────────

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
      <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('cleanup.history.title', 'Cleanup History')}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Datum', 'Aktion', 'Verarbeitet', 'Gelöscht', 'Freigegeben'].map((h) => (
                <th
                  key={h}
                  className="py-2 px-3 text-left font-medium"
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
                <td className="py-2 px-3" style={{ color: 'var(--text-secondary)' }}>
                  {new Date(entry.performed_at).toLocaleString('de-DE')}
                </td>
                <td className="py-2 px-3">
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                    style={{ background: 'var(--accent-bg)', color: 'var(--accent)' }}
                  >
                    {entry.action_type}
                  </span>
                </td>
                <td
                  className="py-2 px-3 tabular-nums"
                  style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
                >
                  {entry.files_processed}
                </td>
                <td
                  className="py-2 px-3 tabular-nums"
                  style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}
                >
                  {entry.files_deleted}
                </td>
                <td
                  className="py-2 px-3 tabular-nums"
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
        <div className="flex items-center justify-center gap-2 p-3">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-2 py-1 rounded text-xs disabled:opacity-40"
            style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
          >
            Zurück
          </button>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {page} / {Math.ceil(total / 50)}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={page >= Math.ceil(total / 50)}
            className="px-2 py-1 rounded text-xs disabled:opacity-40"
            style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
          >
            Weiter
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export function CleanupSettings() {
  const { t } = useTranslation('settings')
  const { data: rules = [], isLoading } = useCleanupRules()
  const { data: stats } = useCleanupStats()
  const createRule = useCreateCleanupRule()
  const updateRule = useUpdateCleanupRule()
  const deleteRule = useDeleteCleanupRule()
  const runRule = useRunCleanupRule()
  const rulePreview = useRulePreview()
  const startScan = useStartCleanupScan()
  const [isScanning, setIsScanning] = useState(false)
  const scanStatus = useCleanupScanStatus(isScanning)
  const { data: duplicatesData, refetch: refetchDuplicates } = useDuplicates()
  const deleteDuplicates = useDeleteDuplicates()
  const cleanupPreview = useCleanupPreview()

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [showNewModal, setShowNewModal] = useState(false)
  const [previewResult, setPreviewResult] = useState<Record<string, number> | null>(null)
  const [dedupPreviewData, setDedupPreviewData] = useState<CleanupPreviewData | null>(null)
  const [pendingDeleteSelections, setPendingDeleteSelections] = useState<
    { keep: string; delete: string[] }[] | null
  >(null)

  const selectedRule = rules.find((r: CleanupRule) => r.id === selectedId) ?? null

  // Auto-select first rule when rules load
  useEffect(() => {
    if (rules.length > 0 && selectedId === null) setSelectedId(rules[0].id)
  }, [rules, selectedId])

  // Stop scan polling when scan completes
  useEffect(() => {
    if (scanStatus.data?.status === 'idle' && isScanning) {
      setIsScanning(false)
      void refetchDuplicates()
    }
  }, [scanStatus.data, isScanning, refetchDuplicates])

  const handleCreate = useCallback(
    (name: string, ruleType: string) => {
      createRule.mutate(
        {
          name,
          rule_type: ruleType as CleanupRule['rule_type'],
          config_json: {},
          enabled: true,
          schedule: 'manual',
        },
        {
          onSuccess: (rule: CleanupRule) => {
            setSelectedId(rule.id)
            setShowNewModal(false)
          },
          onError: () => toast('Fehler beim Erstellen der Regel', 'error'),
        },
      )
    },
    [createRule],
  )

  const handleUpdate = useCallback(
    (patch: Partial<CleanupRule>) => {
      if (!selectedId) return
      updateRule.mutate(
        { id: selectedId, data: patch },
        { onError: () => toast('Fehler beim Speichern', 'error') },
      )
    },
    [selectedId, updateRule],
  )

  const handleDelete = useCallback(() => {
    if (!selectedId) return
    deleteRule.mutate(selectedId, {
      onSuccess: () => {
        setSelectedId(null)
        toast('Regel gelöscht')
      },
      onError: () => toast('Fehler beim Löschen', 'error'),
    })
  }, [selectedId, deleteRule])

  const handleRun = useCallback(() => {
    if (!selectedId) return
    runRule.mutate(selectedId, {
      onSuccess: () => toast('Regel erfolgreich ausgeführt'),
      onError: () => toast('Fehler beim Ausführen', 'error'),
    })
  }, [selectedId, runRule])

  const handlePreview = useCallback(() => {
    if (!selectedId) return
    rulePreview.mutate(selectedId, {
      onSuccess: (data: { preview: Record<string, number> }) => setPreviewResult(data.preview),
      onError: () => toast('Vorschau fehlgeschlagen', 'error'),
    })
  }, [selectedId, rulePreview])

  const handleStartScan = useCallback(() => {
    startScan.mutate(undefined, {
      onSuccess: () => setIsScanning(true),
      onError: () => toast('Scan fehlgeschlagen', 'error'),
    })
  }, [startScan])

  const handleDeleteDuplicates = useCallback(
    (selections: { keep: string; delete: string[] }[]) => {
      setPendingDeleteSelections(selections)
      cleanupPreview.mutate(undefined, {
        onSuccess: (data: CleanupPreviewData) => setDedupPreviewData(data),
        onError: () => {
          deleteDuplicates.mutate(selections, {
            onSuccess: (result: { deleted: number; bytes_freed: number }) => {
              toast(
                `${result.deleted} Dateien gelöscht, ${formatBytes(result.bytes_freed)} freigegeben`,
              )
              setPendingDeleteSelections(null)
            },
            onError: () => toast('Fehler beim Löschen', 'error'),
          })
        },
      })
    },
    [cleanupPreview, deleteDuplicates],
  )

  const handleConfirmDedupDelete = useCallback(() => {
    if (!pendingDeleteSelections) return
    deleteDuplicates.mutate(pendingDeleteSelections, {
      onSuccess: (result: { deleted: number; bytes_freed: number }) => {
        toast(
          `${result.deleted} Dateien gelöscht, ${formatBytes(result.bytes_freed)} freigegeben`,
        )
        setPendingDeleteSelections(null)
        setDedupPreviewData(null)
      },
      onError: () => toast('Fehler beim Löschen', 'error'),
    })
  }, [pendingDeleteSelections, deleteDuplicates])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  const groups = duplicatesData?.groups ?? []

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="px-6 py-5" style={{ borderBottom: '1px solid var(--border)' }}>
        <PageHeader
          title={t('cleanup.page.title', 'Cleanup Rules')}
          subtitle={t(
            'cleanup.page.subtitle',
            'Automatisierte Bereinigung von Sidecar-Dateien und Datenbankeinträgen',
          )}
        />
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <RuleSidebar
          rules={rules}
          selectedId={selectedId}
          onSelect={(id) => {
            setSelectedId(id)
            setPreviewResult(null)
          }}
          onNew={() => setShowNewModal(true)}
        />

        {/* Main content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Disk space */}
          {stats && <DiskSpaceWidget stats={stats} />}

          {/* Rule detail or empty state */}
          {selectedRule ? (
            <RuleDetail
              rule={selectedRule}
              previewResult={previewResult}
              isRunning={runRule.isPending}
              isPreviewing={rulePreview.isPending}
              onRun={handleRun}
              onPreview={handlePreview}
              onDelete={handleDelete}
              onUpdate={handleUpdate}
            />
          ) : (
            <div
              className="rounded-xl p-12 text-center text-sm"
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                color: 'var(--text-muted)',
              }}
            >
              Wähle eine Regel aus der Sidebar oder erstelle eine neue.
            </div>
          )}

          {/* Deduplication section */}
          <div
            className="rounded-xl overflow-hidden"
            style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div
              className="flex items-center justify-between px-4 py-3"
              style={{ borderBottom: '1px solid var(--border)' }}
            >
              <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                {t('cleanup.dedup.title', 'Deduplication')}
              </span>
              <button
                onClick={handleStartScan}
                disabled={isScanning || startScan.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white disabled:opacity-50"
                style={{ background: 'var(--accent)' }}
              >
                {isScanning ? <Loader2 size={12} className="animate-spin" /> : null}
                {isScanning
                  ? 'Scannt...'
                  : t('cleanup.dedup.scanButton', 'Scan for Duplicates')}
              </button>
            </div>
            <div className="p-4">
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
                  onDelete={handleDeleteDuplicates}
                  isDeleting={deleteDuplicates.isPending}
                />
              ) : (
                <div
                  className="text-sm text-center py-4"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {t('cleanup.dedup.noResults', 'No duplicates found. Run a scan to check.')}
                </div>
              )}
            </div>
          </div>

          <HistorySection />
        </div>
      </div>

      {showNewModal && (
        <NewRuleModal onClose={() => setShowNewModal(false)} onCreate={handleCreate} />
      )}
    </div>
  )
}
