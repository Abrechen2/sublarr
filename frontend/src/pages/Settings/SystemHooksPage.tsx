import { Suspense, useState } from 'react'
import { Webhook, History } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormLayout } from '@/components/settings/layouts'
import type { FormSectionDef } from '@/components/settings/layouts'
import { toast } from '@/components/shared/Toast'
import {
  useHookConfigs, useCreateHook, useUpdateHook, useDeleteHook, useTestHook,
  useHookLogs, useClearHookLogs, useEventCatalog,
} from '@/hooks/useIntegrationApi'
import { Loader2, Plus, Edit2, Trash2, TestTube, X } from 'lucide-react'
import type { HookConfig } from '@/lib/types'
import { WebhooksSection } from './connections/WebhooksSection'

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
  const { t } = useTranslation('settings')
  const { t: tc } = useTranslation('common')
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
            {initialData ? t('system_hooks_page.edit_hook') : t('system_hooks_page.new_hook')}
          </h3>
          <button onClick={onCancel} style={{ color: 'var(--text-muted)' }}>
            <X size={14} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{t('system_hooks_page.form.name')}</label>
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
            <label className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{t('system_hooks_page.form.event')}</label>
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
            <label className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{t('system_hooks_page.form.script_path')}</label>
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
          <button className="btn-secondary text-sm" onClick={onCancel}>{tc('actions.cancel')}</button>
          <button
            className="btn-primary text-sm"
            onClick={() => onSave(form)}
            disabled={isPending || !form.name.trim() || !form.script_path.trim()}
            style={{ backgroundColor: 'var(--accent)', color: 'white', border: 'none', borderRadius: '6px', padding: '6px 14px', cursor: 'pointer' }}
          >
            {isPending ? <Loader2 size={14} className="animate-spin inline mr-1" /> : null}
            {t('system_hooks_page.save')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Outgoing Hooks Section ───────────────────────────────────────────────────

function OutgoingHooksSection() {
  const { t } = useTranslation('common')
  const { t: tc } = useTranslation('common')
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
        onSuccess: () => { setShowModal(false); setEditingHook(null); toast(t('settings:system_hooks_page.toast_hook_updated')) },
        onError: () => toast(t('settings:system_hooks_page.toast_hook_update_failed'), 'error'),
      })
    } else {
      createHook.mutate(form, {
        onSuccess: () => { setShowModal(false); toast(t('settings:system_hooks_page.toast_hook_created')) },
        onError: () => toast(t('settings:system_hooks_page.toast_hook_create_failed'), 'error'),
      })
    }
  }

  const handleTest = (id: number) => {
    testHookMut.mutate(id, {
      onSuccess: (r: { success?: boolean; message?: string }) => {
        toast(r.message ?? (r.success ? t('settings:system_hooks_page.toast_test_succeeded') : t('settings:system_hooks_page.toast_test_failed')))
      },
      onError: () => toast(t('settings:system_hooks_page.toast_test_failed'), 'error'),
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
          {t('settings:system_hooks_page.new_hook')}
        </button>
      </div>

      {hooks.length === 0 && (
        <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
          {t('settings:system_hooks_page.no_hooks')}
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
              title={t('settings:system_hooks_page.action.test')}
              onClick={() => handleTest(hook.id)}
              className="p-1.5 rounded"
              style={{ color: 'var(--text-muted)', border: '1px solid var(--border)' }}
              data-testid={`test-hook-${hook.id}`}
            >
              <TestTube size={13} />
            </button>
            <button
              title={t('settings:system_hooks_page.action.edit')}
              onClick={() => { setEditingHook(hook); setShowModal(true) }}
              className="p-1.5 rounded"
              style={{ color: 'var(--text-muted)', border: '1px solid var(--border)' }}
              data-testid={`edit-hook-${hook.id}`}
            >
              <Edit2 size={13} />
            </button>
            <button
              title={t('settings:system_hooks_page.action.delete')}
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
            <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>{t('settings:system_hooks_page.confirm_delete_title')}</h3>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{tc('common.undo_warning')}</p>
            <div className="flex gap-2 justify-end">
              <button className="btn-secondary text-sm" onClick={() => setDeleteConfirmId(null)}>{tc('actions.cancel')}</button>
              <button
                className="text-sm px-3 py-1.5 rounded"
                style={{ backgroundColor: 'var(--error)', color: 'white', border: 'none', cursor: 'pointer' }}
                onClick={() => {
                  deleteHook.mutate(deleteConfirmId, {
                    onSuccess: () => { setDeleteConfirmId(null); toast(t('settings:system_hooks_page.toast_hook_deleted')) },
                    onError: () => { setDeleteConfirmId(null); toast(t('settings:system_hooks_page.toast_delete_failed'), 'error') },
                  })
                }}
              >
                {t('settings:system_hooks_page.delete')}
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
  const { t } = useTranslation('common')
  const { t: tc } = useTranslation('common')
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
          {t('settings:system_hooks_page.clear_logs')}
        </button>
      </div>

      {logList.length === 0 ? (
        <div className="text-center py-6 text-sm" style={{ color: 'var(--text-muted)' }}>{t('settings:system_hooks_page.logs.empty')}</div>
      ) : (
        <div className="overflow-x-auto rounded-lg" style={{ border: '1px solid var(--border)' }}>
          <table className="w-full text-xs">
            <thead>
              <tr style={{ backgroundColor: 'var(--bg-surface-hover)', color: 'var(--text-muted)' }}>
                <th className="px-3 py-2 text-left">{t('settings:system_hooks_page.logs.timestamp')}</th>
                <th className="px-3 py-2 text-left">{t('settings:system_hooks_page.col_hook')}</th>
                <th className="px-3 py-2 text-left">{t('settings:system_hooks_page.logs.event')}</th>
                <th className="px-3 py-2 text-left">{t('settings:system_hooks_page.logs.status')}</th>
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
                      {log.success ? t('settings:system_hooks_page.status_ok') : t('settings:system_hooks_page.status_failed')}
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
            <h3 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>{t('settings:system_hooks_page.confirm_clear_title')}</h3>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{tc('common.undo_warning')}</p>
            <div className="flex gap-2 justify-end">
              <button className="btn-secondary text-sm" onClick={() => setShowClearConfirm(false)}>{tc('actions.cancel')}</button>
              <button
                className="text-sm px-3 py-1.5 rounded"
                style={{ backgroundColor: 'var(--error)', color: 'white', border: 'none', cursor: 'pointer' }}
                onClick={() => {
                  clearLogs.mutate(undefined, {
                    onSuccess: () => { setShowClearConfirm(false); toast(t('settings:system_hooks_page.toast_logs_cleared')) },
                    onError: () => { setShowClearConfirm(false); toast(t('settings:system_hooks_page.toast_clear_failed'), 'error') },
                  })
                }}
              >
                {t('settings:system_hooks_page.clear')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── SystemHooksPage ──────────────────────────────────────────────────────────

// Settings Template B (FormLayout). Three TOC groups; the Webhooks group
// internally renders one card per service (Sonarr / Radarr / Jellyfin) but
// shows up as a SINGLE TOC entry — that's how users think of it ("the
// webhooks part of the page"), so a 3-card sub-list under one anchor is
// correct UX.
const SECTIONS: readonly FormSectionDef[] = [
  { id: 'webhooks', titleKey: 'hooks_page.webhooks_section' },
  { id: 'outgoing', titleKey: 'hooks_page.outgoing_section' },
  { id: 'logs',     titleKey: 'hooks_page.logs_section' },
]

export function SystemHooksPage() {
  const { t } = useTranslation('settings')
  const { t: tCommon } = useTranslation('common')

  return (
    <SettingsDetailLayout
      title={t('system_hooks_page.title')}
      subtitle={t('system_hooks_page.subtitle')}
    >
      <FormLayout sections={SECTIONS}>

        {/* 1. Webhooks (incoming integrations) — three service cards under one anchor */}
        <section id="webhooks" data-testid="settings.system-hooks.section-webhooks">
          <WebhooksSection />
        </section>

        {/* 2. Shell Hooks (outgoing) */}
        <section id="outgoing" data-testid="settings.system-hooks.section-outgoing">
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
        </section>

        {/* 3. Execution Log */}
        <section id="logs" data-testid="settings.system-hooks.section-logs">
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
        </section>

      </FormLayout>
    </SettingsDetailLayout>
  )
}
