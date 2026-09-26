import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { FileText, Eye, Package } from 'lucide-react'
import {
  fetchSupportPreview,
  downloadSupportBundle,
  getConfig,
  updateConfig,
} from '@/api/client'
import { useLogRotation, useUpdateLogRotation } from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'
import { SettingsCard } from '@/components/shared/SettingsCard'
import type { SupportPreview } from '@/lib/types'

// ─── Log viewer preferences (localStorage, client-side only) ─────────────────

const PREFS_KEY = 'sublarr_log_view_prefs'

interface LogViewPrefs {
  categories: Record<string, boolean>
  showTimestamps: boolean
  wrapLines: boolean
}

const DEFAULT_PREFS: LogViewPrefs = {
  categories: {
    scanner: true,
    translation: true,
    providers: true,
    jobs: true,
    auth: true,
  },
  showTimestamps: true,
  wrapLines: false,
}

function loadPrefs(): LogViewPrefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    return raw ? { ...DEFAULT_PREFS, ...JSON.parse(raw) } : DEFAULT_PREFS
  } catch {
    return DEFAULT_PREFS
  }
}

function savePrefs(prefs: LogViewPrefs): void {
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
}

// ─── Support export modal ─────────────────────────────────────────────────────

/**
 * Renders any object/array-shaped value as a plain key/value list. Used for
 * the support-preview sections the backend is adding alongside `diagnostic`
 * and `redaction_summary` (database, scheduler, circuit breakers, queues,
 * foreign-track sweep, track policy, tool versions): every one of them is
 * optional and its exact shape may still change on the backend side, so this
 * stays generic instead of hard-coding field names that would go stale.
 */
function renderSupportValue(value: unknown, boolYes: string, boolNo: string): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? boolYes : boolNo
  if (typeof value === 'number' || typeof value === 'string') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function isRateLimited(err: unknown): boolean {
  return (err as { response?: { status?: number } } | null)?.response?.status === 429
}

function SupportGenericSection({ title, data }: { title: string; data: unknown }) {
  const { t } = useTranslation('settings')
  if (data === null || data === undefined) return null

  const boolYes = t('support_bool_yes')
  const boolNo = t('support_bool_no')

  let rows: { key: string; value: unknown }[]
  if (Array.isArray(data)) {
    rows = data.flatMap((item, index) => {
      if (item !== null && typeof item === 'object' && !Array.isArray(item)) {
        return Object.entries(item as Record<string, unknown>).map(([k, v]) => ({
          key: `${index}.${k}`,
          value: v,
        }))
      }
      return [{ key: String(index), value: item }]
    })
  } else if (typeof data === 'object') {
    rows = Object.entries(data as Record<string, unknown>).map(([key, value]) => ({ key, value }))
  } else {
    rows = [{ key: title, value: data }]
  }

  if (rows.length === 0) return null

  return (
    <div className="mb-4 rounded-lg border border-border bg-page p-4 text-sm space-y-1.5">
      <p className="font-medium mb-1">{title}</p>
      {rows.map(({ key, value }) => (
        <div key={key} className="flex justify-between gap-3 text-secondary">
          <span className="font-mono text-xs">{key}</span>
          <span className="text-right break-all">{renderSupportValue(value, boolYes, boolNo)}</span>
        </div>
      ))}
    </div>
  )
}

export function SupportModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation('settings')
  const [downloading, setDownloading] = useState(false)

  const { data, isLoading, isError } = useQuery<SupportPreview>({
    queryKey: ['support-preview'],
    queryFn: fetchSupportPreview,
    staleTime: 0,
    retry: 1,
  })

  const handleDownload = async () => {
    setDownloading(true)
    try {
      await downloadSupportBundle()
    } catch (err) {
      toast(t(isRateLimited(err) ? 'support_rate_limited' : 'support_modal_error'), 'error')
    } finally {
      setDownloading(false)
    }
  }

  const diag = data?.diagnostic
  const rs = data?.redaction_summary

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="support-modal-title"
        className="w-full max-w-lg rounded-xl p-6 shadow-xl"
        style={{ background: 'var(--bg-surface)', maxHeight: '85vh', overflowY: 'auto' }}
      >
        <h2 id="support-modal-title" className="mb-4 text-lg font-semibold">
          {t('support_modal_title')}
        </h2>

        {isLoading && (
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {t('support_modal_loading')}
          </p>
        )}

        {isError && !data && (
          <p className="mb-3 text-sm" style={{ color: 'var(--text-error, #f87171)' }}>
            {t('support_modal_error')}
          </p>
        )}

        {diag && (
          <div
            className="mb-4 rounded-lg p-4 text-sm space-y-3"
            style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
          >
            <p className="font-medium">{t('support_diagnostic_title')}</p>
            <p style={{ color: 'var(--text-secondary)' }}>
              Sublarr {diag.version} · {diag.timestamp_utc}
            </p>
            {(diag.uptime_minutes != null || diag.memory_mb != null) && (
              <p style={{ color: 'var(--text-secondary)' }}>
                {diag.uptime_minutes != null &&
                  `${t('support_uptime')}: ${Math.floor(diag.uptime_minutes / 60)}h ${diag.uptime_minutes % 60}m`}
                {diag.uptime_minutes != null && diag.memory_mb != null && '  ·  '}
                {diag.memory_mb != null && `${t('support_memory')}: ${diag.memory_mb} MB`}
              </p>
            )}
            <div>
              <p className="font-medium mb-1">{t('support_top_errors')}</p>
              {diag.top_errors.length === 0 ? (
                <p style={{ color: 'var(--text-secondary)' }}>{t('support_no_errors')}</p>
              ) : (
                <ul className="space-y-0.5">
                  {diag.top_errors.slice(0, 5).map((e, i) => (
                    <li key={i} style={{ color: 'var(--text-secondary)' }}>
                      ✗ {e.message} (×{e.count})
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {diag.provider_status.length > 0 && (
              <div>
                <p className="font-medium mb-1">{t('support_providers')}</p>
                <p style={{ color: 'var(--text-secondary)' }}>
                  {diag.provider_status
                    .map(p => `${p.active ? '●' : '○'} ${p.name}`)
                    .join('  ')}
                </p>
              </div>
            )}
            {!diag.db_stats_error && diag.wanted && (
              <p style={{ color: 'var(--text-secondary)' }}>
                {t('support_wanted_label')}: {diag.wanted.total} · {t('support_pending_label')}:{' '}
                {diag.wanted.pending} · {t('support_failed_label')}: {diag.wanted.failed}
              </p>
            )}
          </div>
        )}

        {rs && (
          <div
            className="mb-4 rounded-lg p-4 text-sm space-y-2"
            style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
          >
            <p className="font-medium">{t('support_redaction_title')}</p>
            <p style={{ color: 'var(--text-secondary)' }}>
              {rs.log_files_found} {t('support_log_files')} · {rs.ips_redacted}{' '}
              {t('support_ips_label')} · {rs.api_keys_redacted} {t('support_keys_label')} ·{' '}
              {rs.paths_redacted} {t('support_paths_label').toLowerCase()}
            </p>
            {rs.example_path_before && (
              <div className="mt-2">
                <p className="text-xs font-medium">{t('support_paths_label')}:</p>
                <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                  <span className="font-sans font-medium">{t('support_before')}:</span>{' '}
                  {rs.example_path_before}
                </p>
                <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                  <span className="font-sans font-medium">{t('support_after')}:</span>{' '}
                  {rs.example_path_after}
                </p>
              </div>
            )}
            {rs.example_ip_before && (
              <div className="mt-1">
                <p className="text-xs font-medium">{t('support_ips_label')}:</p>
                <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                  <span className="font-sans font-medium">{t('support_before')}:</span>{' '}
                  {rs.example_ip_before}
                </p>
                <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                  <span className="font-sans font-medium">{t('support_after')}:</span>{' '}
                  {rs.example_ip_after}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Additional bundle sections — all optional, rendered generically
            since the backend adds/renames these independently of this UI. */}
        {Object.entries(data?.sections ?? {}).map(([name, section]) => (
          <SupportGenericSection
            key={name}
            title={t(`support_section_${name}`, { defaultValue: name })}
            data={section}
          />
        ))}

        <div className="flex justify-end gap-3">
          <button
            autoFocus
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm"
            style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
          >
            {t('support_modal_cancel')}
          </button>
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="rounded-lg px-4 py-2 text-sm font-medium"
            style={{ background: 'var(--bg-accent)', color: 'var(--text-on-accent)' }}
          >
            {downloading ? '...' : t('support_modal_download')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main tab component ───────────────────────────────────────────────────────

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR'] as const

export function ProtokollTab() {
  const { t } = useTranslation('settings')
  const { t: tc } = useTranslation('common')
  const queryClient = useQueryClient()

  // Log-level (uses the same settings API as the rest of the settings page)
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: getConfig })
  const { mutate: saveConfig } = useMutation({
    mutationFn: (patch: Record<string, unknown>) => updateConfig(patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
      toast(t('saved', { ns: 'common' }), 'success')
    },
  })

  // Log rotation — defaults mirror backend/app_logging.py
  // LOG_MAX_SIZE_MB_DEFAULT / LOG_BACKUP_COUNT_DEFAULT (10 MB / 5 files), so
  // this input never flashes a different value than what a fresh install
  // actually runs with before the query resolves.
  const { data: rotation } = useLogRotation()
  const updateRotation = useUpdateLogRotation()
  const [maxSize, setMaxSize] = useState(10)
  const [backupCount, setBackupCount] = useState(5)

  useEffect(() => {
    if (rotation) {
      setMaxSize(rotation.max_size_mb ?? 10)
      setBackupCount(rotation.backup_count ?? 5)
    }
  }, [rotation])

  const handleSaveRotation = () => {
    updateRotation.mutate(
      { max_size_mb: maxSize, backup_count: backupCount },
      // The backend now reloads and re-applies rotation live (no restart
      // needed) — say so instead of the generic "saved" toast, which used to
      // leave it open whether the change had actually taken effect.
      {
        onSuccess: (result) =>
          result?.live === false
            ? toast(t('log_rotation_saved_restart'), 'info')
            : toast(t('log_rotation_saved_live'), 'success'),
      },
    )
  }

  // Log viewer prefs (localStorage)
  const [prefs, setPrefs] = useState<LogViewPrefs>(loadPrefs)
  const [showModal, setShowModal] = useState(false)

  const toggleCategory = (key: string) => {
    const next = { ...prefs, categories: { ...prefs.categories, [key]: !prefs.categories[key] } }
    setPrefs(next)
    savePrefs(next)
  }

  const togglePref = (key: 'showTimestamps' | 'wrapLines') => {
    const next = { ...prefs, [key]: !prefs[key] }
    setPrefs(next)
    savePrefs(next)
  }

  // No "API Requests" category: under Gunicorn (Sublarr's only deployment
  // target) access logging goes through gunicorn's own "gunicorn.access"
  // logger straight to stdout/Docker logs, never through the app's log
  // handlers — so a werkzeug-based filter here could never fire.
  const CATEGORIES = [
    { key: 'scanner',     label: t('category_scanner') },
    { key: 'translation', label: t('category_translation') },
    { key: 'providers',   label: t('category_providers') },
    { key: 'jobs',        label: t('category_jobs') },
    { key: 'auth',        label: t('category_auth') },
  ]

  return (
    <div className="space-y-6">
      {/* ── Log Settings ── */}
      <SettingsCard title={t('log_settings')} icon={FileText}>
        <div className="space-y-4 p-4">
          {/* Log level */}
          <div>
            <label className="block text-sm font-medium mb-1">{tc('ui.log_level')}</label>
            <select
              value={(config as Record<string, string> | undefined)?.log_level ?? 'INFO'}
              onChange={e => saveConfig({ log_level: e.target.value })}
              className="rounded-lg px-3 py-2 text-sm"
              style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
            >
              {LOG_LEVELS.map(l => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>

          {/* Log rotation */}
          <p className="text-sm font-medium">{t('log_rotation')}</p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm mb-1">{t('max_size_mb')}</label>
              <input
                type="number" min={1} max={100} value={maxSize}
                onChange={e => setMaxSize(Math.min(100, Math.max(1, Number(e.target.value))))}
                className="w-full rounded-lg px-3 py-2 text-sm"
                style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
              />
            </div>
            <div>
              <label className="block text-sm mb-1">{t('backup_count')}</label>
              <input
                type="number" min={1} max={20} value={backupCount}
                onChange={e => setBackupCount(Math.min(20, Math.max(1, Number(e.target.value))))}
                className="w-full rounded-lg px-3 py-2 text-sm"
                style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
              />
            </div>
          </div>
          <button
            onClick={handleSaveRotation}
            disabled={updateRotation.isPending}
            className="rounded-lg px-4 py-2 text-sm font-medium"
            style={{ background: 'var(--bg-accent)', color: 'var(--text-on-accent)' }}
          >
            {updateRotation.isPending ? '...' : t('save', { ns: 'common' })}
          </button>
        </div>
      </SettingsCard>

      {/* ── Log Viewer Display ── */}
      <SettingsCard title={t('log_viewer_display')} icon={Eye}>
        <div className="space-y-3 p-4">
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {t('log_viewer_display_desc')}
          </p>
          <div className="grid grid-cols-2 gap-2">
            {CATEGORIES.map(cat => (
              <label key={cat.key} className="flex items-center gap-2 cursor-pointer text-sm">
                <input
                  type="checkbox"
                  checked={prefs.categories[cat.key] ?? true}
                  onChange={() => toggleCategory(cat.key)}
                  className="rounded"
                />
                {cat.label}
              </label>
            ))}
          </div>
          <div className="border-t pt-3 space-y-2" style={{ borderColor: 'var(--border)' }}>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input type="checkbox" checked={prefs.showTimestamps}
                onChange={() => togglePref('showTimestamps')} className="rounded" />
              {t('show_timestamps')}
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input type="checkbox" checked={prefs.wrapLines}
                onChange={() => togglePref('wrapLines')} className="rounded" />
              {t('wrap_lines')}
            </label>
          </div>
        </div>
      </SettingsCard>

      {/* ── Support ── */}
      <SettingsCard title={t('support_section')} icon={Package}>
        <div className="p-4">
          <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
            {t('support_section_desc')}
          </p>
          <button
            onClick={() => setShowModal(true)}
            className="rounded-lg px-4 py-2 text-sm font-medium"
            style={{ background: 'var(--bg-accent)', color: 'var(--text-on-accent)' }}
          >
            {t('support_export_button')}
          </button>
        </div>
      </SettingsCard>

      {showModal && <SupportModal onClose={() => setShowModal(false)} />}
    </div>
  )
}
