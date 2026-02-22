import { useState, useEffect } from 'react'
import {
  useEventCatalog, useHookConfigs, useCreateHook, useUpdateHook, useDeleteHook, useTestHook,
  useWebhookConfigs, useCreateWebhook, useUpdateWebhook, useDeleteWebhook, useTestWebhook,
  useHookLogs, useClearHookLogs,
  useScoringWeights, useUpdateScoringWeights, useResetScoringWeights,
  useProviderModifiers, useUpdateProviderModifiers,
  useProviders,
  useConfig, useUpdateConfig,
} from '@/hooks/useApi'
import { Save, Loader2, TestTube, ChevronUp, ChevronDown, Trash2, Plus, Edit2, X, Check, Eye, EyeOff, CheckCircle, XCircle, RotateCcw } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { Toggle } from '@/components/shared/Toggle'
import { SettingSection } from '@/components/shared/SettingSection'
import type { EventCatalogItem, HookConfig, WebhookConfig, HookLog, ScoringWeights } from '@/lib/types'

// ─── Events & Hooks Tab ──────────────────────────────────────────────────────

export function EventsHooksTab() {
  const { data: eventCatalog } = useEventCatalog()
  const { data: hooks } = useHookConfigs()
  const { data: webhooks } = useWebhookConfigs()
  const { data: logs } = useHookLogs()
  const createHook = useCreateHook()
  const updateHook = useUpdateHook()
  const deleteHook = useDeleteHook()
  const testHookMut = useTestHook()
  const createWebhook = useCreateWebhook()
  const updateWebhook = useUpdateWebhook()
  const deleteWebhook = useDeleteWebhook()
  const testWebhookMut = useTestWebhook()
  const clearLogs = useClearHookLogs()

  const [hooksOpen, setHooksOpen] = useState(true)
  const [webhooksOpen, setWebhooksOpen] = useState(true)
  const [logsOpen, setLogsOpen] = useState(false)

  // Hook add/edit form
  const [hookForm, setHookForm] = useState<{ name: string; event_name: string; script_path: string; timeout_seconds: number } | null>(null)
  const [editingHookId, setEditingHookId] = useState<number | null>(null)

  // Webhook add/edit form
  const [webhookForm, setWebhookForm] = useState<{ name: string; event_name: string; url: string; secret: string; retry_count: number; timeout_seconds: number } | null>(null)
  const [editingWebhookId, setEditingWebhookId] = useState<number | null>(null)
  const [showWebhookSecret, setShowWebhookSecret] = useState(false)

  // Expanded log rows
  const [expandedLog, setExpandedLog] = useState<number | null>(null)

  const events: EventCatalogItem[] = eventCatalog || []
  const hookList: HookConfig[] = hooks || []
  const webhookList: WebhookConfig[] = webhooks || []
  const logList: HookLog[] = logs || []

  const handleCreateHook = () => {
    if (!hookForm) return
    if (editingHookId !== null) {
      updateHook.mutate({ id: editingHookId, data: hookForm }, {
        onSuccess: () => { setHookForm(null); setEditingHookId(null); toast('Hook updated') },
        onError: () => toast('Failed to update hook', 'error'),
      })
    } else {
      createHook.mutate(hookForm, {
        onSuccess: () => { setHookForm(null); toast('Hook created') },
        onError: () => toast('Failed to create hook', 'error'),
      })
    }
  }

  const handleCreateWebhook = () => {
    if (!webhookForm) return
    if (editingWebhookId !== null) {
      updateWebhook.mutate({ id: editingWebhookId, data: webhookForm }, {
        onSuccess: () => { setWebhookForm(null); setEditingWebhookId(null); toast('Webhook updated') },
        onError: () => toast('Failed to update webhook', 'error'),
      })
    } else {
      createWebhook.mutate(webhookForm, {
        onSuccess: () => { setWebhookForm(null); toast('Webhook created') },
        onError: () => toast('Failed to create webhook', 'error'),
      })
    }
  }

  return (
    <div className="space-y-4">
      {/* Shell Hooks Section */}
      <div className="rounded-lg overflow-hidden" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <button
          onClick={() => setHooksOpen(!hooksOpen)}
          className="w-full flex items-center justify-between px-4 py-3 text-left"
        >
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Shell Hooks</span>
          {hooksOpen ? <ChevronUp size={16} style={{ color: 'var(--text-muted)' }} /> : <ChevronDown size={16} style={{ color: 'var(--text-muted)' }} />}
        </button>
        {hooksOpen && (
          <div className="px-4 pb-4 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
            {hookList.map((hook) => (
              <div key={hook.id} className="rounded-md p-3 space-y-2" style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{hook.name}</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium" style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}>
                      {hook.event_name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Toggle
                      checked={hook.enabled}
                      onChange={() => updateHook.mutate({ id: hook.id, data: { enabled: !hook.enabled } })}
                    />
                    <button
                      onClick={() => { setEditingHookId(hook.id); setHookForm({ name: hook.name, event_name: hook.event_name, script_path: hook.script_path, timeout_seconds: hook.timeout_seconds }) }}
                      className="p-1 rounded hover:opacity-80" style={{ color: 'var(--text-muted)' }}
                    ><Edit2 size={13} /></button>
                    <button
                      onClick={() => testHookMut.mutate(hook.id, {
                        onSuccess: (r) => toast(r.success ? `Test passed (exit ${r.exit_code})` : `Test failed: ${r.stderr || r.error}`, r.success ? 'success' : 'error'),
                        onError: () => toast('Test failed', 'error'),
                      })}
                      disabled={testHookMut.isPending}
                      className="p-1 rounded hover:opacity-80" style={{ color: 'var(--accent)' }}
                    >{testHookMut.isPending ? <Loader2 size={13} className="animate-spin" /> : <TestTube size={13} />}</button>
                    <button
                      onClick={() => { if (confirm('Delete this hook?')) deleteHook.mutate(hook.id) }}
                      className="p-1 rounded hover:opacity-80" style={{ color: 'var(--error)' }}
                    ><Trash2 size={13} /></button>
                  </div>
                </div>
                <div className="flex items-center gap-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{hook.script_path}</span>
                  {hook.trigger_count > 0 && <span>{hook.trigger_count} triggers</span>}
                  {hook.last_triggered_at && <span>Last: {new Date(hook.last_triggered_at).toLocaleString()}</span>}
                </div>
              </div>
            ))}

            {/* Hook form */}
            {hookForm ? (
              <div className="rounded-md p-3 space-y-2" style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--accent-dim)' }}>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    value={hookForm.name} onChange={(e) => setHookForm({ ...hookForm, name: e.target.value })}
                    placeholder="Hook name"
                    className="px-2 py-1.5 rounded text-sm" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                  />
                  <select
                    value={hookForm.event_name} onChange={(e) => setHookForm({ ...hookForm, event_name: e.target.value })}
                    className="px-2 py-1.5 rounded text-sm" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                  >
                    <option value="">Select event...</option>
                    {events.map((ev) => <option key={ev.name} value={ev.name}>{ev.label}</option>)}
                  </select>
                </div>
                <div className="grid grid-cols-[1fr_auto] gap-2">
                  <input
                    value={hookForm.script_path} onChange={(e) => setHookForm({ ...hookForm, script_path: e.target.value })}
                    placeholder="/config/hooks/my-script.sh"
                    className="px-2 py-1.5 rounded text-sm" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
                  />
                  <input
                    type="number" value={hookForm.timeout_seconds} onChange={(e) => setHookForm({ ...hookForm, timeout_seconds: parseInt(e.target.value) || 30 })}
                    className="w-20 px-2 py-1.5 rounded text-sm text-center" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                    title="Timeout (seconds)"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={handleCreateHook} disabled={createHook.isPending || updateHook.isPending}
                    className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white" style={{ backgroundColor: 'var(--accent)' }}>
                    <Check size={12} />{editingHookId ? 'Update' : 'Create'}
                  </button>
                  <button onClick={() => { setHookForm(null); setEditingHookId(null) }} className="px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
                    <X size={12} />
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setHookForm({ name: '', event_name: '', script_path: '', timeout_seconds: 30 })}
                className="flex items-center gap-1.5 px-3 py-2 rounded-md text-xs font-medium" style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
              ><Plus size={13} /> Add Hook</button>
            )}
          </div>
        )}
      </div>

      {/* Outgoing Webhooks Section */}
      <div className="rounded-lg overflow-hidden" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <button
          onClick={() => setWebhooksOpen(!webhooksOpen)}
          className="w-full flex items-center justify-between px-4 py-3 text-left"
        >
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Outgoing Webhooks</span>
          {webhooksOpen ? <ChevronUp size={16} style={{ color: 'var(--text-muted)' }} /> : <ChevronDown size={16} style={{ color: 'var(--text-muted)' }} />}
        </button>
        {webhooksOpen && (
          <div className="px-4 pb-4 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
            {webhookList.map((wh) => (
              <div key={wh.id} className="rounded-md p-3 space-y-2" style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{wh.name}</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium" style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}>
                      {wh.event_name === '*' ? 'All Events' : wh.event_name}
                    </span>
                    {wh.last_status_code > 0 && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium" style={{
                        backgroundColor: wh.last_status_code >= 200 && wh.last_status_code < 300 ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                        color: wh.last_status_code >= 200 && wh.last_status_code < 300 ? 'var(--success)' : 'var(--error)',
                      }}>
                        {wh.last_status_code}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Toggle
                      checked={wh.enabled}
                      onChange={() => updateWebhook.mutate({ id: wh.id, data: { enabled: !wh.enabled } })}
                    />
                    <button
                      onClick={() => { setEditingWebhookId(wh.id); setWebhookForm({ name: wh.name, event_name: wh.event_name, url: wh.url, secret: wh.secret, retry_count: wh.retry_count, timeout_seconds: wh.timeout_seconds }) }}
                      className="p-1 rounded hover:opacity-80" style={{ color: 'var(--text-muted)' }}
                    ><Edit2 size={13} /></button>
                    <button
                      onClick={() => testWebhookMut.mutate(wh.id, {
                        onSuccess: (r) => toast(r.success ? `OK (${r.status_code})` : `Failed: ${r.error || r.status_code}`, r.success ? 'success' : 'error'),
                        onError: () => toast('Test failed', 'error'),
                      })}
                      disabled={testWebhookMut.isPending}
                      className="p-1 rounded hover:opacity-80" style={{ color: 'var(--accent)' }}
                    >{testWebhookMut.isPending ? <Loader2 size={13} className="animate-spin" /> : <TestTube size={13} />}</button>
                    <button
                      onClick={() => { if (confirm('Delete this webhook?')) deleteWebhook.mutate(wh.id) }}
                      className="p-1 rounded hover:opacity-80" style={{ color: 'var(--error)' }}
                    ><Trash2 size={13} /></button>
                  </div>
                </div>
                <div className="flex items-center gap-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{wh.url.length > 50 ? wh.url.slice(0, 50) + '...' : wh.url}</span>
                  {wh.consecutive_failures > 0 && <span style={{ color: 'var(--error)' }}>{wh.consecutive_failures} failures</span>}
                  {wh.trigger_count > 0 && <span>{wh.trigger_count} triggers</span>}
                </div>
              </div>
            ))}

            {/* Webhook form */}
            {webhookForm ? (
              <div className="rounded-md p-3 space-y-2" style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--accent-dim)' }}>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    value={webhookForm.name} onChange={(e) => setWebhookForm({ ...webhookForm, name: e.target.value })}
                    placeholder="Webhook name"
                    className="px-2 py-1.5 rounded text-sm" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                  />
                  <select
                    value={webhookForm.event_name} onChange={(e) => setWebhookForm({ ...webhookForm, event_name: e.target.value })}
                    className="px-2 py-1.5 rounded text-sm" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                  >
                    <option value="">Select event...</option>
                    <option value="*">All Events</option>
                    {events.map((ev) => <option key={ev.name} value={ev.name}>{ev.label}</option>)}
                  </select>
                </div>
                <input
                  value={webhookForm.url} onChange={(e) => setWebhookForm({ ...webhookForm, url: e.target.value })}
                  placeholder="https://example.com/webhook"
                  className="w-full px-2 py-1.5 rounded text-sm" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
                />
                <div className="grid grid-cols-[1fr_auto_auto] gap-2">
                  <div className="relative">
                    <input
                      type={showWebhookSecret ? 'text' : 'password'}
                      value={webhookForm.secret} onChange={(e) => setWebhookForm({ ...webhookForm, secret: e.target.value })}
                      placeholder="Secret (optional, for HMAC signing)"
                      className="w-full px-2 py-1.5 rounded text-sm pr-8" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                    />
                    <button onClick={() => setShowWebhookSecret(!showWebhookSecret)} className="absolute right-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }}>
                      {showWebhookSecret ? <EyeOff size={13} /> : <Eye size={13} />}
                    </button>
                  </div>
                  <input
                    type="number" value={webhookForm.retry_count} onChange={(e) => setWebhookForm({ ...webhookForm, retry_count: parseInt(e.target.value) || 3 })}
                    className="w-16 px-2 py-1.5 rounded text-sm text-center" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                    title="Retries"
                  />
                  <input
                    type="number" value={webhookForm.timeout_seconds} onChange={(e) => setWebhookForm({ ...webhookForm, timeout_seconds: parseInt(e.target.value) || 10 })}
                    className="w-16 px-2 py-1.5 rounded text-sm text-center" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                    title="Timeout (seconds)"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={handleCreateWebhook} disabled={createWebhook.isPending || updateWebhook.isPending}
                    className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white" style={{ backgroundColor: 'var(--accent)' }}>
                    <Check size={12} />{editingWebhookId ? 'Update' : 'Create'}
                  </button>
                  <button onClick={() => { setWebhookForm(null); setEditingWebhookId(null); setShowWebhookSecret(false) }} className="px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
                    <X size={12} />
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setWebhookForm({ name: '', event_name: '', url: '', secret: '', retry_count: 3, timeout_seconds: 10 })}
                className="flex items-center gap-1.5 px-3 py-2 rounded-md text-xs font-medium" style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
              ><Plus size={13} /> Add Webhook</button>
            )}
          </div>
        )}
      </div>

      {/* Execution Log Section */}
      <div className="rounded-lg overflow-hidden" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <button
          onClick={() => setLogsOpen(!logsOpen)}
          className="w-full flex items-center justify-between px-4 py-3 text-left"
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Execution Log</span>
            {logList.length > 0 && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium" style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}>
                {logList.length}
              </span>
            )}
          </div>
          {logsOpen ? <ChevronUp size={16} style={{ color: 'var(--text-muted)' }} /> : <ChevronDown size={16} style={{ color: 'var(--text-muted)' }} />}
        </button>
        {logsOpen && (
          <div className="px-4 pb-4 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
            {logList.length > 0 && (
              <div className="flex justify-end pt-2">
                <button
                  onClick={() => { if (confirm('Clear all execution logs?')) clearLogs.mutate(undefined, { onSuccess: () => toast('Logs cleared') }) }}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[11px]" style={{ color: 'var(--error)' }}
                ><Trash2 size={11} /> Clear Logs</button>
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    <th className="text-left py-1.5 px-2 font-medium" style={{ color: 'var(--text-muted)' }}>Time</th>
                    <th className="text-left py-1.5 px-2 font-medium" style={{ color: 'var(--text-muted)' }}>Event</th>
                    <th className="text-left py-1.5 px-2 font-medium" style={{ color: 'var(--text-muted)' }}>Type</th>
                    <th className="text-left py-1.5 px-2 font-medium" style={{ color: 'var(--text-muted)' }}>Status</th>
                    <th className="text-right py-1.5 px-2 font-medium" style={{ color: 'var(--text-muted)' }}>Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {logList.map((log) => (
                    <>
                      <tr
                        key={log.id}
                        onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
                        className="cursor-pointer hover:opacity-80"
                        style={{ borderBottom: '1px solid var(--border)' }}
                      >
                        <td className="py-1.5 px-2" style={{ color: 'var(--text-secondary)' }}>{new Date(log.triggered_at).toLocaleString()}</td>
                        <td className="py-1.5 px-2" style={{ color: 'var(--text-primary)' }}>{log.event_name}</td>
                        <td className="py-1.5 px-2">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium" style={{
                            backgroundColor: log.hook_type === 'script' ? 'rgba(139,92,246,0.15)' : 'rgba(59,130,246,0.15)',
                            color: log.hook_type === 'script' ? '#8b5cf6' : '#3b82f6',
                          }}>{log.hook_type}</span>
                        </td>
                        <td className="py-1.5 px-2">
                          {log.success ? <CheckCircle size={14} style={{ color: 'var(--success)' }} /> : <XCircle size={14} style={{ color: 'var(--error)' }} />}
                        </td>
                        <td className="py-1.5 px-2 text-right" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{log.duration_ms}ms</td>
                      </tr>
                      {expandedLog === log.id && (
                        <tr key={`${log.id}-detail`}>
                          <td colSpan={5} className="px-2 py-2">
                            <div className="rounded p-2 text-[11px] space-y-1" style={{ backgroundColor: 'var(--bg-primary)', fontFamily: 'var(--font-mono)' }}>
                              {log.stdout && <div><span style={{ color: 'var(--text-muted)' }}>stdout:</span> <span style={{ color: 'var(--text-secondary)' }}>{log.stdout}</span></div>}
                              {log.stderr && <div><span style={{ color: 'var(--text-muted)' }}>stderr:</span> <span style={{ color: 'var(--error)' }}>{log.stderr}</span></div>}
                              {log.error && <div><span style={{ color: 'var(--text-muted)' }}>error:</span> <span style={{ color: 'var(--error)' }}>{log.error}</span></div>}
                              {log.exit_code !== null && <div><span style={{ color: 'var(--text-muted)' }}>exit_code:</span> {log.exit_code}</div>}
                              {log.status_code !== null && <div><span style={{ color: 'var(--text-muted)' }}>status_code:</span> {log.status_code}</div>}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
            {logList.length === 0 && (
              <p className="text-center text-xs py-4" style={{ color: 'var(--text-muted)' }}>No execution logs yet.</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Scoring Tab ────────────────────────────────────────────────────────────

export function ScoringTab() {
  const { data: scoringData } = useScoringWeights()
  const { data: providers } = useProviders()
  const { data: modifiers } = useProviderModifiers()
  const updateWeights = useUpdateScoringWeights()
  const resetWeights = useResetScoringWeights()
  const updateModifiers = useUpdateProviderModifiers()

  const [episodeWeights, setEpisodeWeights] = useState<Record<string, number>>({})
  const [movieWeights, setMovieWeights] = useState<Record<string, number>>({})
  const [providerMods, setProviderMods] = useState<Record<string, number>>({})
  const [weightsInit, setWeightsInit] = useState(false)
  const [modsInit, setModsInit] = useState(false)

  const weights: ScoringWeights | undefined = scoringData
  const providerList = providers?.providers || []

  useEffect(() => {
    if (weights && !weightsInit) {
      setEpisodeWeights(weights.episode)
      setMovieWeights(weights.movie)
      setWeightsInit(true)
    }
  }, [weights, weightsInit])

  useEffect(() => {
    if (modifiers && !modsInit) {
      const mods: Record<string, number> = { ...modifiers }
      for (const p of providerList) {
        if (!(p.name in mods)) mods[p.name] = 0
      }
      setProviderMods(mods)
      setModsInit(true)
    }
  }, [modifiers, providerList, modsInit])

  const handleSaveWeights = () => {
    updateWeights.mutate({ episode: episodeWeights, movie: movieWeights }, {
      onSuccess: () => toast('Scoring weights saved'),
      onError: () => toast('Failed to save weights', 'error'),
    })
  }

  const handleResetWeights = () => {
    if (!confirm('Reset all scoring weights to defaults?')) return
    resetWeights.mutate(undefined, {
      onSuccess: () => {
        setWeightsInit(false)
        toast('Scoring weights reset to defaults')
      },
      onError: () => toast('Failed to reset weights', 'error'),
    })
  }

  const handleSaveModifiers = () => {
    const toSave: Record<string, number> = {}
    for (const [name, mod] of Object.entries(providerMods)) {
      if (mod !== 0) toSave[name] = mod
    }
    updateModifiers.mutate(toSave, {
      onSuccess: () => toast('Provider modifiers saved'),
      onError: () => toast('Failed to save modifiers', 'error'),
    })
  }

  const formatWeightKey = (key: string) => {
    if (key === 'format_bonus') return 'ASS Format Bonus'
    if (key === 'hearing_impaired') return 'Hearing Impaired'
    if (key === 'release_group') return 'Release Group'
    if (key === 'audio_codec') return 'Audio Codec'
    return key.charAt(0).toUpperCase() + key.slice(1)
  }

  const renderWeightTable = (
    label: string,
    currentWeights: Record<string, number>,
    setFn: (w: Record<string, number>) => void,
    defaults: Record<string, number> | undefined
  ) => (
    <div className="flex-1 min-w-[280px]">
      <h4 className="text-xs font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>{label}</h4>
      <div className="space-y-1">
        {Object.entries(currentWeights).map(([key, value]) => (
          <div key={key} className="flex items-center justify-between gap-2">
            <span className="text-[12px]" style={{ color: 'var(--text-secondary)' }}>{formatWeightKey(key)}</span>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={value}
                onChange={(e) => setFn({ ...currentWeights, [key]: parseInt(e.target.value) || 0 })}
                className="w-20 px-2 py-1 rounded text-[12px] text-right"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
              />
              {defaults && (
                <span className="text-[10px] w-8 text-right" style={{ color: 'var(--text-muted)' }}>
                  {defaults[key] ?? ''}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )

  return (
    <div className="space-y-4">
      {/* Scoring Weights */}
      <SettingSection
        title="Scoring Weights"
        description="Higher weights = more important match criteria. Default values shown in grey."
      >
        <div className="flex items-center justify-end gap-2 -mt-1">
          <button
            onClick={handleResetWeights}
            disabled={resetWeights.isPending}
            className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium" style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
          >
            <RotateCcw size={11} /> Reset to Defaults
          </button>
          <button
            onClick={handleSaveWeights}
            disabled={updateWeights.isPending}
            className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white" style={{ backgroundColor: 'var(--accent)' }}
          >
            {updateWeights.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            Save
          </button>
        </div>
        <div className="flex flex-wrap gap-6">
          {renderWeightTable('Episode Weights', episodeWeights, setEpisodeWeights, weights?.defaults?.episode)}
          {renderWeightTable('Movie Weights', movieWeights, setMovieWeights, weights?.defaults?.movie)}
        </div>
      </SettingSection>

      {/* Provider Modifiers */}
      <SettingSection
        title="Provider Modifiers"
        description="Add bonus (positive) or penalty (negative) to all results from a specific provider."
      >
        <div className="flex items-center justify-end -mt-1">
          <button
            onClick={handleSaveModifiers}
            disabled={updateModifiers.isPending}
            className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white" style={{ backgroundColor: 'var(--accent)' }}
          >
            {updateModifiers.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            Save All
          </button>
        </div>
        <div className="space-y-2">
          {Object.entries(providerMods).sort(([a], [b]) => a.localeCompare(b)).map(([name, mod]) => (
            <div key={name} className="flex items-center justify-between gap-3">
              <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>{name}</span>
              <div className="flex items-center gap-2">
                <input
                  type="range" min={-100} max={100} value={mod}
                  onChange={(e) => setProviderMods({ ...providerMods, [name]: parseInt(e.target.value) })}
                  className="w-32"
                />
                <span className="w-10 text-right text-[12px] font-medium" style={{
                  fontFamily: 'var(--font-mono)',
                  color: mod > 0 ? 'var(--success)' : mod < 0 ? 'var(--error)' : 'var(--text-muted)',
                }}>
                  {mod > 0 ? `+${mod}` : mod}
                </span>
              </div>
            </div>
          ))}
          {Object.keys(providerMods).length === 0 && (
            <p className="text-center text-xs py-3" style={{ color: 'var(--text-muted)' }}>No providers available.</p>
          )}
        </div>
      </SettingSection>

      {/* Machine Translation Detection */}
      <MtDetectionSection />
    </div>
  )
}


// ─── MT Detection Section ─────────────────────────────────────────────────────

function MtDetectionSection() {
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()

  const [penalty, setPenalty] = useState<number>(-30)
  const [threshold, setThreshold] = useState<number>(50)
  const [init, setInit] = useState(false)

  useEffect(() => {
    if (configData && !init) {
      const p = configData['providers.mt_penalty']
      const t = configData['providers.mt_confidence_threshold']
      if (p !== undefined) setPenalty(Number(p))
      if (t !== undefined) setThreshold(Number(t))
      setInit(true)
    }
  }, [configData, init])

  const handleSave = () => {
    updateConfig.mutate(
      { 'providers.mt_penalty': penalty, 'providers.mt_confidence_threshold': threshold },
      {
        onSuccess: () => toast('MT detection settings saved'),
        onError: () => toast('Failed to save MT detection settings', 'error'),
      }
    )
  }

  return (
    <SettingSection
      title="Machine Translation Detection"
      description="Subtitles detected as machine-translated receive a score penalty. Set penalty to 0 to disable. Threshold: minimum confidence (0-100) required to apply the penalty."
    >
      <div className="flex items-center justify-end -mt-1">
        <button
          onClick={handleSave}
          disabled={updateConfig.isPending}
          className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {updateConfig.isPending ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          Save
        </button>
      </div>
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>MT Score Penalty</span>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Applied to machine-translated subtitles (-50 to 0; 0 = disabled)
            </p>
          </div>
          <input
            type="number"
            min={-50}
            max={0}
            value={penalty}
            onChange={(e) => setPenalty(Math.max(-50, Math.min(0, parseInt(e.target.value) || 0)))}
            className="w-20 px-2 py-1 rounded text-[12px] text-right"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
            }}
          />
        </div>
        <div className="flex items-center justify-between gap-3">
          <div>
            <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>MT Confidence Threshold</span>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Minimum confidence % (0-100) to flag as machine-translated
            </p>
          </div>
          <input
            type="number"
            min={0}
            max={100}
            value={threshold}
            onChange={(e) => setThreshold(Math.max(0, Math.min(100, parseInt(e.target.value) || 0)))}
            className="w-20 px-2 py-1 rounded text-[12px] text-right"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
            }}
          />
        </div>
      </div>
    </SettingSection>
  )
}
