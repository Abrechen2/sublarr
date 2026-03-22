import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useConfig, useUpdateConfig,
  useNotificationTemplates, useCreateNotificationTemplate, useUpdateNotificationTemplate, useDeleteNotificationTemplate,
  useNotificationFilters, useUpdateNotificationFilters,
  useEventCatalog,
} from '@/hooks/useApi'
import { TemplateEditor } from '@/components/notifications/TemplateEditor'
import { TemplatePreview } from '@/components/notifications/TemplatePreview'
import { toast } from '@/components/shared/Toast'
import {
  Loader2, Plus, Trash2, Edit3, Save, X, Bell, BellOff,
  ChevronDown, ChevronRight, Filter, TestTube,
} from 'lucide-react'
import type { NotificationTemplate, NotificationFilter } from '@/lib/types'

// ─── Notification Toggles (legacy compat) ────────────────────────────────────

function NotificationToggles() {
  const { t } = useTranslation('settings')
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()

  const toggles = [
    { key: 'notify_on_download', label: t('notifications.on_download', 'Notify on Download') },
    { key: 'notify_on_upgrade', label: t('notifications.on_upgrade', 'Notify on Upgrade') },
    { key: 'notify_on_batch_complete', label: t('notifications.on_batch_complete', 'Notify on Batch Complete') },
    { key: 'notify_on_error', label: t('notifications.on_error', 'Notify on Error') },
    { key: 'notify_manual_actions', label: t('notifications.manual_actions', 'Notify Manual Actions') },
  ]

  const handleToggle = (key: string) => {
    const current = String(config?.[key] ?? 'false')
    const newVal = current === 'true' ? 'false' : 'true'
    updateConfig.mutate({ [key]: newVal })
  }

  const handleTestNotification = async () => {
    try {
      const { testNotification } = await import('@/api/client')
      const result = await testNotification()
      if (result.success) {
        toast('Test notification sent!')
      } else {
        toast(result.message || 'Test failed', 'error')
      }
    } catch {
      toast('Failed to send test notification', 'error')
    }
  }

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          <Bell size={14} className="inline mr-1.5" />
          {t('notifications.toggles', 'Notification Events')}
        </h3>
        <button
          onClick={() => void handleTestNotification()}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all duration-150"
          style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--accent-bg)' }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
        >
          <TestTube size={12} />
          Test
        </button>
      </div>

      {/* Apprise URLs */}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          Notification URLs (Apprise)
        </label>
        <textarea
          value={String(config?.notification_urls_json ?? '')}
          onChange={(e) => updateConfig.mutate({ notification_urls_json: e.target.value })}
          placeholder={'One URL per line, e.g.:\npushover://user@token\ndiscord://webhook_id/webhook_token'}
          rows={3}
          className="w-full px-3 py-2 rounded-md text-xs focus:outline-none resize-y"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
          }}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {toggles.map((toggle) => {
          const enabled = String(config?.[toggle.key] ?? 'false') === 'true'
          return (
            <button
              key={toggle.key}
              onClick={() => handleToggle(toggle.key)}
              className="flex items-center gap-2 px-3 py-2 rounded-md text-xs transition-all duration-150"
              style={{
                backgroundColor: enabled ? 'var(--accent-bg)' : 'var(--bg-primary)',
                border: `1px solid ${enabled ? 'var(--accent-dim)' : 'var(--border)'}`,
                color: enabled ? 'var(--accent)' : 'var(--text-muted)',
              }}
            >
              {enabled ? <Bell size={12} /> : <BellOff size={12} />}
              {toggle.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ─── Templates Section ───────────────────────────────────────────────────────

function TemplatesSection() {
  const { t } = useTranslation('settings')
  const { data, isLoading } = useNotificationTemplates()
  const createTemplate = useCreateNotificationTemplate()
  const updateTemplate = useUpdateNotificationTemplate()
  const deleteTemplate = useDeleteNotificationTemplate()

  const [editingId, setEditingId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState<Partial<NotificationTemplate>>({
    name: '', title_template: '', body_template: '', event_type: null, service_name: null, enabled: true,
  })

  const templates = data?.templates ?? []

  const handleCreate = () => {
    setCreating(true)
    setEditingId(null)
    setDraft({ name: '', title_template: '', body_template: '', event_type: null, service_name: null, enabled: true })
  }

  const handleEdit = (template: NotificationTemplate) => {
    setEditingId(template.id)
    setCreating(false)
    setDraft({ ...template })
  }

  const handleSave = () => {
    if (creating) {
      createTemplate.mutate(draft, {
        onSuccess: () => { setCreating(false); setDraft({}); toast('Template created') },
        onError: () => toast('Failed to create template', 'error'),
      })
    } else if (editingId !== null) {
      updateTemplate.mutate({ id: editingId, data: draft }, {
        onSuccess: () => { setEditingId(null); setDraft({}); toast('Template updated') },
        onError: () => toast('Failed to update template', 'error'),
      })
    }
  }

  const handleDelete = (id: number) => {
    deleteTemplate.mutate(id, {
      onSuccess: () => { if (editingId === id) { setEditingId(null); setDraft({}) }; toast('Template deleted') },
      onError: () => toast('Failed to delete template', 'error'),
    })
  }

  const handleCancel = () => {
    setCreating(false)
    setEditingId(null)
    setDraft({})
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-20">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('notifications.templates.title', 'Templates')}
        </h3>
        <button
          onClick={handleCreate}
          disabled={creating}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all duration-150"
          style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
        >
          <Plus size={12} />
          {t('notifications.templates.create', 'New Template')}
        </button>
      </div>

      {/* Template List */}
      {templates.map((tmpl) => (
        <div
          key={tmpl.id}
          className="rounded-lg overflow-hidden"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center justify-between px-4 py-2.5">
            <div className="flex items-center gap-2 min-w-0">
              <Bell size={14} style={{ color: tmpl.enabled ? 'var(--accent)' : 'var(--text-muted)' }} />
              <span className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                {tmpl.name}
              </span>
              {tmpl.event_type && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}>
                  {tmpl.event_type}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => handleEdit(tmpl)}
                className="p-1.5 rounded transition-colors"
                style={{ color: 'var(--text-muted)' }}
                onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
                onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
              >
                <Edit3 size={14} />
              </button>
              <button
                onClick={() => handleDelete(tmpl.id)}
                className="p-1.5 rounded transition-colors"
                style={{ color: 'var(--text-muted)' }}
                onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
                onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>

          {editingId === tmpl.id && (
            <div className="px-4 pb-4 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
              <div className="pt-3">
                <TemplateEditor template={draft} onChange={(update) => setDraft((prev) => ({ ...prev, ...update }))} />
              </div>
              <TemplatePreview
                templateId={tmpl.id}
                titleTemplate={draft.title_template}
                bodyTemplate={draft.body_template}
              />
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSave}
                  disabled={updateTemplate.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
                  style={{ backgroundColor: 'var(--accent)' }}
                >
                  {updateTemplate.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                  Save
                </button>
                <button onClick={handleCancel} className="px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
                  <X size={12} className="inline mr-1" />Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      ))}

      {/* Create Form */}
      {creating && (
        <div
          className="rounded-lg p-4 space-y-3"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--accent-dim)' }}
        >
          <TemplateEditor template={draft} onChange={(update) => setDraft((prev) => ({ ...prev, ...update }))} />
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={createTemplate.isPending || !draft.name?.trim()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {createTemplate.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
              Create
            </button>
            <button onClick={handleCancel} className="px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
              <X size={12} className="inline mr-1" />Cancel
            </button>
          </div>
        </div>
      )}

      {templates.length === 0 && !creating && (
        <div
          className="rounded-lg p-6 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <Bell size={24} className="mx-auto mb-2" style={{ color: 'var(--text-muted)' }} />
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            No templates yet. Create one to customize notification content.
          </p>
        </div>
      )}
    </div>
  )
}

// ─── Filters Section ─────────────────────────────────────────────────────────

function FiltersSection() {
  const { t } = useTranslation('settings')
  const { data: filtersData, isLoading } = useNotificationFilters()
  const updateFilters = useUpdateNotificationFilters()
  const { data: catalogData } = useEventCatalog()
  const [expanded, setExpanded] = useState(false)

  const eventTypes = catalogData?.events
    ? (catalogData.events as { name: string; label: string }[])
    : []

  const filters: NotificationFilter = filtersData ?? { include_events: [], exclude_events: [], content_filters: [] }

  const toggleEvent = (list: 'include_events' | 'exclude_events', eventName: string) => {
    const current = filters[list] ?? []
    const updated = current.includes(eventName)
      ? current.filter((e) => e !== eventName)
      : [...current, eventName]
    updateFilters.mutate({ ...filters, [list]: updated }, {
      onSuccess: () => toast('Filters updated'),
      onError: () => toast('Failed to update filters', 'error'),
    })
  }

  return (
    <div className="space-y-2">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 text-sm font-semibold"
        style={{ color: 'var(--text-primary)' }}
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Filter size={14} />
        {t('notifications.filters.title', 'Event Filters')}
      </button>

      {expanded && (
        <div
          className="rounded-lg p-4 space-y-3"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          {isLoading ? (
            <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent)' }} />
          ) : (
            <>
              <div className="space-y-1.5">
                <label className="block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  {t('notifications.filters.exclude', 'Exclude Events')}
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {eventTypes.map((evt) => {
                    const excluded = filters.exclude_events.includes(evt.name)
                    return (
                      <button
                        key={evt.name}
                        onClick={() => toggleEvent('exclude_events', evt.name)}
                        className="px-2 py-1 rounded text-[10px] font-medium transition-all duration-150"
                        style={{
                          backgroundColor: excluded ? 'var(--error-bg, rgba(239,68,68,0.1))' : 'var(--bg-primary)',
                          color: excluded ? 'var(--error)' : 'var(--text-muted)',
                          border: `1px solid ${excluded ? 'var(--error)' : 'var(--border)'}`,
                        }}
                      >
                        {evt.label || evt.name}
                      </button>
                    )
                  })}
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  {t('notifications.filters.include', 'Include Only (if set, only these events)')}
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {eventTypes.map((evt) => {
                    const included = filters.include_events.includes(evt.name)
                    return (
                      <button
                        key={evt.name}
                        onClick={() => toggleEvent('include_events', evt.name)}
                        className="px-2 py-1 rounded text-[10px] font-medium transition-all duration-150"
                        style={{
                          backgroundColor: included ? 'var(--success-bg, rgba(34,197,94,0.1))' : 'var(--bg-primary)',
                          color: included ? 'var(--success)' : 'var(--text-muted)',
                          border: `1px solid ${included ? 'var(--success)' : 'var(--border)'}`,
                        }}
                      >
                        {evt.label || evt.name}
                      </button>
                    )
                  })}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Main NotificationTemplatesTab ───────────────────────────────────────────

export function NotificationTemplatesTab() {
  return (
    <div className="space-y-6">
      <NotificationToggles />
      <TemplatesSection />
      <FiltersSection />
    </div>
  )
}
