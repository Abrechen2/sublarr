import { Suspense, useState } from 'react'
import { Copy, Webhook, History } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { SettingRow } from '@/components/shared/SettingRow'
import { toast } from '@/components/shared/Toast'
import {
  useHookConfigs, useCreateHook, useUpdateHook, useDeleteHook, useTestHook,
  useHookLogs, useClearHookLogs, useEventCatalog,
} from '@/hooks/useIntegrationApi'
import { Loader2, Plus, Edit2, Trash2, TestTube, X } from 'lucide-react'
import type { HookConfig } from '@/lib/types'

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function SectionSkeleton() {
  return (
    <div className="animate-pulse space-y-3 py-2">
      {[...Array(3)].map((_, i) => (
        <div
          key={i}
          className="h-8 rounded"
          style={{ backgroundColor: 'var(--bg-surface-hover)', width: i === 0 ? '70%' : '100%' }}
        />
      ))}
    </div>
  )
}

// ─── Hook Form ────────────────────────────────────────────────────────────────

type HookFormData = { name: string; event_name: string; script_path: string; timeout_seconds: number }

function HookFormModal({
  initialData,
  eventNames,
  onSave,
  onCancel,
  isPending,
}: {
  initialData: HookFormData | null
  eventNames: string[]
  onSave: (data: HookFormData) => void
  onCancel: () => void
  isPending: boolean
}) {
  const [form, setForm] = useState<HookFormData>(
    initialData ?? { name: '', event_name: eventNames[0] ?? '', script_path: '', timeout_seconds: 30 }
  )

  const update = (field: keyof HookFormData, value: string | number) =>
    setForm((prev) => ({ ...prev, [field]: value }))

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-md mx-4 rounded-xl p-5 space-y-4"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
            {initialData ? 'Edit Hook' : 'New Hook'}
          </h3>
          <button onClick={onCancel} style={{ color: 'var(--text-muted)' }}>
            <X size={14} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Name *</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => update('name', e.target.value)}
              className="w-full mt-1 px-3 py-2 rounded text-sm"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              data-testid="hook-form-name"
            />
          </div>
          <div>
            <label className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Event *</label>
            <select
              value={form.event_name}
              onChange={(e) => update('event_name', e.target.value)}
              className="w-full mt-1 px-3 py-2 rounded text-sm"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              data-testid="hook-form-event"
            >
              {eventNames.map((e) => <option key={e} value={e}>{e}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Script path *</label>
            <input
              type="text"
              value={form.script_path}
              onChange={(e) => update('script_path', e.target.value)}
              className="w-full mt-1 px-3 py-2 rounded text-sm font-mono"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              data-testid="hook-form-script-path"
            />
          </div>
        </div>

        <div className="flex gap-2 justify-end pt-1">
          <button className="btn-secondary text-sm" onClick={onCancel}>Cancel</button>
          <button
            className="btn-primary text-sm"
            onClick={() => onSave(form)}
            disabled={isPending || !form.name.trim() || !form.script_path.trim()}
            style={{ backgroundColor: 'var(--accent)', color: 'white', border: 'none', borderRadius: '6px', padding: '6px 14px', cursor: 'pointer' }}
          >
            {isPending ? <Loader2 size={14} className="animate-spin inline mr-1" /> : null}
            Save
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Outgoing Hooks Section ───────────────────────────────────────────────────

function OutgoingHooksSection() {
  const { data: hookData } = useHookConfigs()
  const { data: catalogData } = useEventCatalog()
  const createHook = useCreateHook()
  const updateHook = useUpdateHook()
  const deleteHook = useDeleteHook()
  const testHookMut = useTestHook()

  const [showModal, setShowModal] = useState(false)
  const [editingHook, setEditingHook] = useState<HookConfig | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)

  const hooks: HookConfig[] = hookData ?? []
  const eventNames = (catalogData as { name: string }[] | undefined)?.map((e) => e.name) ?? []

  const handleSave = (form: HookFormData) => {
    if (editingHook) {
      updateHook.mutate({ id: editingHook.id, data: form }, {
        onSuccess: () => { setShowModal(false); setEditingHook(null); toast('Hook updated') },
        onError: () => toast('Failed to update hook', 'error'),
      })
    } else {
      createHook.mutate(form, {
        onSuccess: () => { setShowModal(false); toast('Hook created') },
        onError: () => toast('Failed to create hook', 'error'),
      })
    }
  }

  const handleTest = (id: number) => {
    testHookMut.mutate(id, {
      onSuccess: (r: { success?: boolean; message?: string }) => {
        toast(r.message ?? (r.success ? 'Hook test succeeded' : 'Hook test failed'))
      },
      onError: () => toast('Hook test failed', 'error'),
    })
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button
          className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded"
          style={{ backgroundColor: 'var(--accent)', color: 'white', border: 'none', cursor: 'pointer' }}
          onClick={() => { setEditingHook(null); setShowModal(true) }}
          data-testid="new-hook-btn"
        >
          <Plus size={14} />
          New Hook
        </button>
      </div>

      {hooks.length === 0 && (
        <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
          No hooks configured yet. Create one to run scripts on events.
        </div>
      )}

      {hooks.map((hook) => (
        <div
          key={hook.id}
          className="flex items-center gap-3 p-3 rounded-lg"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <div className="flex-1 min-w-0">
            <div className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>{hook.name}</div>
            <div className="text-xs mt-0.5 flex items-center gap-2" style={{ color: 'var(--text-muted)' }}>
              <span
                className="px-1.5 py-0.5 rounded text-[10px]"
                style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
              >
                {hook.event_name}
              </span>
              <span className="truncate max-w-[200px] font-mono">{hook.script_path}</span>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              title="Test hook"
              onClick={() => handleTest(hook.id)}
              className="p-1.5 rounded"
              style={{ color: 'var(--text-muted)', border: '1px solid var(--border)' }}
              data-testid={`test-hook-${hook.id}`}
            >
              <TestTube size={13} />
            </button>
            <button
              title="Edit hook"
              onClick={() => { setEditingHook(hook); setShowModal(true) }}
              className="p-1.5 rounded"
              style={{ color: 'var(--text-muted)', border: '1px solid var(--border)' }}
              data-testid={`edit-hook-${hook.id}`}
            >
              <Edit2 size={13} />
            </button>
            <button
              title="Delete hook"
              onClick={() => setDeleteConfirmId(hook.id)}
              className="p-1.5 rounded"
              style={{ color: 'var(--error)', border: '1px solid var(--border)' }}
              data-testid={`delete-hook-${hook.id}`}
            >
              <Trash2 size={13} />
            </button>
          </div>
        </div>
      ))}

      {showModal && (
        <HookFormModal
          initialData={editingHook ? { name: editingHook.name, event_name: editingHook.event_name, script_path: editingHook.script_path, timeout_seconds: editingHook.timeout_seconds } : null}
          eventNames={eventNames}
          onSave={handleSave}
          onCancel={() => { setShowModal(false); setEditingHook(null) }}
          isPending={createHook.isPending || updateHook.isPending}
        />
      )}

      {deleteConfirmId !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="w-full max-w-sm mx-4 rounded-xl p-5 space-y-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Delete hook?</h3>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>This cannot be undone.</p>
            <div className="flex gap-2 justify-end">
              <button className="btn-secondary text-sm" onClick={() => setDeleteConfirmId(null)}>Cancel</button>
              <button
                className="text-sm px-3 py-1.5 rounded"
                style={{ backgroundColor: 'var(--error)', color: 'white', border: 'none', cursor: 'pointer' }}
                onClick={() => {
                  deleteHook.mutate(deleteConfirmId, {
                    onSuccess: () => { setDeleteConfirmId(null); toast('Hook deleted') },
                    onError: () => { setDeleteConfirmId(null); toast('Delete failed', 'error') },
                  })
                }}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Hook Logs Section ────────────────────────────────────────────────────────

function HookLogsSection() {
  const { data: logs } = useHookLogs()
  const clearLogs = useClearHookLogs()
  const [showClearConfirm, setShowClearConfirm] = useState(false)

  const logList = logs ?? []

  return (
    <div className="space-y-3" data-testid="hook-logs-content">
      <div className="flex justify-end">
        <button
          className="flex items-center gap-1.5 text-xs px-2 py-1.5 rounded"
          style={{ border: '1px solid var(--border)', color: 'var(--text-muted)', backgroundColor: 'transparent', cursor: 'pointer' }}
          onClick={() => setShowClearConfirm(true)}
          data-testid="clear-hook-logs-btn"
        >
          <Trash2 size={12} />
          Clear logs
        </button>
      </div>

      {logList.length === 0 ? (
        <div className="text-center py-6 text-sm" style={{ color: 'var(--text-muted)' }}>No hook logs yet.</div>
      ) : (
        <div className="overflow-x-auto rounded-lg" style={{ border: '1px solid var(--border)' }}>
          <table className="w-full text-xs">
            <thead>
              <tr style={{ backgroundColor: 'var(--bg-surface-hover)', color: 'var(--text-muted)' }}>
                <th className="px-3 py-2 text-left">Timestamp</th>
                <th className="px-3 py-2 text-left">Hook</th>
                <th className="px-3 py-2 text-left">Event</th>
                <th className="px-3 py-2 text-left">Status</th>
              </tr>
            </thead>
            <tbody>
              {(logList as { id: number; triggered_at?: string; hook_id?: number; event_name?: string; success?: boolean }[]).map((log) => (
                <tr key={log.id} style={{ borderTop: '1px solid var(--border)', color: 'var(--text-primary)' }}>
                  <td className="px-3 py-2 whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
                    {log.triggered_at ? new Date(log.triggered_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-3 py-2">{log.hook_id ?? '—'}</td>
                  <td className="px-3 py-2">{log.event_name ?? '—'}</td>
                  <td className="px-3 py-2">
                    <span style={{ color: log.success ? 'var(--success)' : 'var(--error)' }}>
                      {log.success ? 'OK' : 'Failed'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showClearConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="w-full max-w-sm mx-4 rounded-xl p-5 space-y-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Clear all hook logs?</h3>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>This cannot be undone.</p>
            <div className="flex gap-2 justify-end">
              <button className="btn-secondary text-sm" onClick={() => setShowClearConfirm(false)}>Cancel</button>
              <button
                className="text-sm px-3 py-1.5 rounded"
                style={{ backgroundColor: 'var(--error)', color: 'white', border: 'none', cursor: 'pointer' }}
                onClick={() => {
                  clearLogs.mutate(undefined, {
                    onSuccess: () => { setShowClearConfirm(false); toast('Hook logs cleared') },
                    onError: () => { setShowClearConfirm(false); toast('Clear failed', 'error') },
                  })
                }}
              >
                Clear
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Webhooks Section ─────────────────────────────────────────────────────────

const WEBHOOKS = [
  { service: 'Sonarr', path: '/api/v1/webhook/sonarr', descKey: 'webhooks_page.sonarr_desc' },
  { service: 'Radarr', path: '/api/v1/webhook/radarr', descKey: 'webhooks_page.radarr_desc' },
  { service: 'Jellyfin', path: '/api/v1/webhook/jellyfin', descKey: 'webhooks_page.jellyfin_desc' },
] as const

function WebhooksSection() {
  const { t } = useTranslation('settings')
  const baseUrl = window.location.origin

  return (
    <div className="space-y-4">
      {WEBHOOKS.map((w) => {
        const fullUrl = `${baseUrl}${w.path}`
        return (
          <SettingsSection
            key={w.service}
            title={w.service}
            description={t(w.descKey)}
            icon={<Webhook size={16} style={{ color: 'var(--accent)' }} />}
          >
            <SettingRow label={t('webhooks_page.webhook_url_label')}>
              <div
                className="flex items-center gap-2"
                style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-muted)' }}
              >
                <span data-testid={`webhook-url-${w.service.toLowerCase()}`}>{fullUrl}</span>
                <button
                  onClick={() => {
                    if (navigator.clipboard) {
                      void navigator.clipboard.writeText(fullUrl)
                    } else {
                      const el = document.createElement('textarea')
                      el.value = fullUrl
                      document.body.appendChild(el)
                      el.select()
                      document.execCommand('copy')
                      document.body.removeChild(el)
                    }
                    toast(t('webhooks_page.copied'))
                  }}
                  className="p-1 rounded transition-colors hover:opacity-80"
                  title={t('webhooks_page.copy_url_title')}
                  style={{ color: 'var(--text-secondary)', flexShrink: 0 }}
                  data-testid={`webhook-copy-${w.service.toLowerCase()}`}
                >
                  <Copy size={14} />
                </button>
              </div>
            </SettingRow>
          </SettingsSection>
        )
      })}
    </div>
  )
}

// ─── SystemHooksPage ──────────────────────────────────────────────────────────

export function SystemHooksPage() {
  const { t } = useTranslation('settings')
  const { t: tCommon } = useTranslation('common')

  return (
    <SettingsDetailLayout
      title={t('system_hooks_page.title')}
      subtitle={t('system_hooks_page.subtitle')}
    >
      {/* 1. Webhooks (incoming integrations) */}
      <WebhooksSection />

      {/* 2. Shell Hooks (outgoing) */}
      <div data-testid="section-outgoing-hooks">
        <SettingsSection
          title={tCommon('settings.hooks.outgoing.title', 'Outgoing Hooks')}
          description={tCommon('settings.hooks.outgoing.description', 'Run local scripts when events occur.')}
          icon={<Webhook size={16} style={{ color: 'var(--accent)' }} />}
        >
          <Suspense fallback={<SectionSkeleton />}>
            <OutgoingHooksSection />
          </Suspense>
        </SettingsSection>
      </div>

      {/* 3. Execution Log */}
      <div data-testid="section-hook-logs">
        <SettingsSection
          title={tCommon('settings.hooks.logs.title', 'Hook Logs')}
          description={tCommon('settings.hooks.logs.description', 'Execution history for all outgoing hooks.')}
          icon={<History size={16} style={{ color: 'var(--accent)' }} />}
        >
          <Suspense fallback={<SectionSkeleton />}>
            <HookLogsSection />
          </Suspense>
        </SettingsSection>
      </div>
    </SettingsDetailLayout>
  )
}
