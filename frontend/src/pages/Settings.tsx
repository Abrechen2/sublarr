import { useState, useEffect } from 'react'
import {
  useConfig, useUpdateConfig, useProviders, useTestProvider, useProviderStats,
  useClearProviderCache, useRetranslateStatus, useRetranslateBatch,
  useLanguageProfiles, useCreateProfile, useUpdateProfile, useDeleteProfile,
} from '@/hooks/useApi'
import { Save, Loader2, TestTube, ChevronUp, ChevronDown, Trash2, Download, Database, RefreshCw, Plus, Edit2, X, Check, Globe } from 'lucide-react'
import { getHealth } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import type { ProviderInfo, LanguageProfile } from '@/lib/types'

const TABS = [
  'General',
  'Ollama',
  'Translation',
  'Languages',
  'Automation',
  'Wanted',
  'Providers',
  'Sonarr',
  'Radarr',
  'Jellyfin',
]

interface FieldConfig {
  key: string
  label: string
  type: 'text' | 'number' | 'password'
  placeholder?: string
  tab: string
}

const FIELDS: FieldConfig[] = [
  // General
  { key: 'port', label: 'Port', type: 'number', tab: 'General' },
  { key: 'api_key', label: 'API Key', type: 'password', placeholder: 'Leave empty to disable', tab: 'General' },
  { key: 'log_level', label: 'Log Level', type: 'text', placeholder: 'INFO', tab: 'General' },
  { key: 'media_path', label: 'Media Path', type: 'text', placeholder: '/media', tab: 'General' },
  { key: 'db_path', label: 'Database Path', type: 'text', placeholder: '/config/sublarr.db', tab: 'General' },
  { key: 'path_mapping', label: 'Path Mapping (Remote\u2192Local)', type: 'text', placeholder: '/data/media=Z:\\Media', tab: 'General' },
  // Ollama
  { key: 'ollama_url', label: 'Ollama URL', type: 'text', placeholder: 'http://localhost:11434', tab: 'Ollama' },
  { key: 'ollama_model', label: 'Model', type: 'text', placeholder: 'qwen2.5:14b-instruct', tab: 'Ollama' },
  { key: 'batch_size', label: 'Batch Size', type: 'number', tab: 'Ollama' },
  { key: 'request_timeout', label: 'Request Timeout (s)', type: 'number', tab: 'Ollama' },
  { key: 'temperature', label: 'Temperature', type: 'number', tab: 'Ollama' },
  // Translation
  { key: 'source_language', label: 'Source Language Code', type: 'text', placeholder: 'en', tab: 'Translation' },
  { key: 'target_language', label: 'Target Language Code', type: 'text', placeholder: 'de', tab: 'Translation' },
  { key: 'source_language_name', label: 'Source Language Name', type: 'text', placeholder: 'English', tab: 'Translation' },
  { key: 'target_language_name', label: 'Target Language Name', type: 'text', placeholder: 'German', tab: 'Translation' },
  // Automation — Upgrade
  { key: 'upgrade_enabled', label: 'Upgrade Enabled', type: 'text', placeholder: 'true', tab: 'Automation' },
  { key: 'upgrade_prefer_ass', label: 'Prefer ASS over SRT', type: 'text', placeholder: 'true', tab: 'Automation' },
  { key: 'upgrade_min_score_delta', label: 'Min Score Delta', type: 'number', placeholder: '50', tab: 'Automation' },
  { key: 'upgrade_window_days', label: 'Upgrade Window (days)', type: 'number', placeholder: '7', tab: 'Automation' },
  // Automation — Webhook
  { key: 'webhook_delay_minutes', label: 'Webhook Delay (minutes)', type: 'number', placeholder: '5', tab: 'Automation' },
  { key: 'webhook_auto_scan', label: 'Auto-Scan after Download', type: 'text', placeholder: 'true', tab: 'Automation' },
  { key: 'webhook_auto_search', label: 'Auto-Search Providers', type: 'text', placeholder: 'true', tab: 'Automation' },
  { key: 'webhook_auto_translate', label: 'Auto-Translate Found Subs', type: 'text', placeholder: 'true', tab: 'Automation' },
  // Automation — Search Scheduler
  { key: 'wanted_search_interval_hours', label: 'Search Interval (hours, 0=disabled)', type: 'number', placeholder: '24', tab: 'Automation' },
  { key: 'wanted_search_on_startup', label: 'Search on Startup', type: 'text', placeholder: 'false', tab: 'Automation' },
  { key: 'wanted_search_max_items_per_run', label: 'Max Items per Search Run', type: 'number', placeholder: '50', tab: 'Automation' },
  // Wanted
  { key: 'wanted_scan_interval_hours', label: 'Scan Interval (hours, 0=disabled)', type: 'number', placeholder: '6', tab: 'Wanted' },
  { key: 'wanted_anime_only', label: 'Anime Only', type: 'text', placeholder: 'true', tab: 'Wanted' },
  { key: 'wanted_scan_on_startup', label: 'Scan on Startup', type: 'text', placeholder: 'true', tab: 'Wanted' },
  { key: 'wanted_max_search_attempts', label: 'Max Search Attempts', type: 'number', placeholder: '3', tab: 'Wanted' },
  // Sonarr
  { key: 'sonarr_url', label: 'Sonarr URL', type: 'text', placeholder: 'http://localhost:8989', tab: 'Sonarr' },
  { key: 'sonarr_api_key', label: 'Sonarr API Key', type: 'password', tab: 'Sonarr' },
  // Radarr
  { key: 'radarr_url', label: 'Radarr URL', type: 'text', placeholder: 'http://localhost:7878', tab: 'Radarr' },
  { key: 'radarr_api_key', label: 'Radarr API Key', type: 'password', tab: 'Radarr' },
  // Jellyfin
  { key: 'jellyfin_url', label: 'Jellyfin URL', type: 'text', placeholder: 'http://localhost:8096', tab: 'Jellyfin' },
  { key: 'jellyfin_api_key', label: 'Jellyfin API Key', type: 'password', tab: 'Jellyfin' },
]

// ─── Provider Card Component ────────────────────────────────────────────────

function ProviderCard({
  provider,
  cacheCount,
  values,
  onFieldChange,
  onTest,
  testResult,
  onMoveUp,
  onMoveDown,
  isFirst,
  isLast,
  onToggle,
  onClearCache,
}: {
  provider: ProviderInfo
  cacheCount: number
  values: Record<string, string>
  onFieldChange: (key: string, value: string) => void
  onTest: () => void
  testResult?: { healthy: boolean; message: string } | 'testing'
  onMoveUp: () => void
  onMoveDown: () => void
  isFirst: boolean
  isLast: boolean
  onToggle: () => void
  onClearCache: () => void
}) {
  const statusColor = !provider.enabled
    ? 'var(--text-muted)'
    : provider.healthy
      ? 'var(--success)'
      : 'var(--error)'

  const statusLabel = !provider.enabled
    ? 'Disabled'
    : provider.initialized
      ? provider.healthy ? 'Healthy' : 'Error'
      : 'Not initialized'

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        opacity: provider.enabled ? 1 : 0.7,
      }}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-semibold capitalize" style={{ color: 'var(--text-primary)' }}>
            {provider.name}
          </span>
          <span
            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium"
            style={{
              backgroundColor: statusColor === 'var(--success)' ? 'var(--success-bg)'
                : statusColor === 'var(--error)' ? 'var(--error-bg)'
                : 'rgba(124,130,147,0.08)',
              color: statusColor,
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: statusColor }}
            />
            {statusLabel}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {/* Enable/Disable toggle */}
          <button
            onClick={onToggle}
            className="px-2.5 py-1 rounded text-xs font-medium transition-all duration-150"
            style={{
              backgroundColor: provider.enabled ? 'var(--accent-bg)' : 'var(--bg-primary)',
              color: provider.enabled ? 'var(--accent)' : 'var(--text-muted)',
              border: '1px solid ' + (provider.enabled ? 'var(--accent-dim)' : 'var(--border)'),
            }}
          >
            {provider.enabled ? 'Enabled' : 'Disabled'}
          </button>

          {/* Test button */}
          <button
            onClick={onTest}
            disabled={!provider.enabled}
            className="p-1.5 rounded transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
              opacity: provider.enabled ? 1 : 0.5,
            }}
            title="Test provider"
          >
            {testResult === 'testing' ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <TestTube size={14} />
            )}
          </button>

          {/* Priority buttons */}
          <button
            onClick={onMoveUp}
            disabled={isFirst}
            className="p-1.5 rounded transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: isFirst ? 'var(--text-muted)' : 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
            }}
            title="Move up (higher priority)"
          >
            <ChevronUp size={14} />
          </button>
          <button
            onClick={onMoveDown}
            disabled={isLast}
            className="p-1.5 rounded transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: isLast ? 'var(--text-muted)' : 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
            }}
            title="Move down (lower priority)"
          >
            <ChevronDown size={14} />
          </button>
        </div>
      </div>

      {/* Test result */}
      {testResult && testResult !== 'testing' && (
        <div className="text-xs" style={{ color: testResult.healthy ? 'var(--success)' : 'var(--error)' }}>
          Test: {testResult.message}
        </div>
      )}

      {/* Status message */}
      {provider.message && provider.message !== 'OK' && provider.message !== 'Not initialized' && (
        <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {provider.message}
        </div>
      )}

      {/* Stats row */}
      <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--text-secondary)' }}>
        <span className="flex items-center gap-1">
          <Download size={12} />
          {provider.downloads} downloads
        </span>
        <span className="flex items-center gap-1">
          <Database size={12} />
          {cacheCount} cached
        </span>
        {cacheCount > 0 && (
          <button
            onClick={onClearCache}
            className="flex items-center gap-1 transition-all duration-150 hover:opacity-80"
            style={{ color: 'var(--text-muted)' }}
            title="Clear cache for this provider"
          >
            <Trash2 size={11} />
            clear
          </button>
        )}
      </div>

      {/* Credential fields */}
      {provider.config_fields.length > 0 && (
        <div className="space-y-2 pt-1" style={{ borderTop: '1px solid var(--border)' }}>
          {provider.config_fields.map((field) => (
            <div key={field.key} className="flex items-center gap-2">
              <label className="text-xs font-medium shrink-0 w-20" style={{ color: 'var(--text-secondary)' }}>
                {field.label}
              </label>
              <input
                type={field.type}
                value={values[field.key] === '***configured***' ? '' : (values[field.key] ?? '')}
                onChange={(e) => onFieldChange(field.key, e.target.value)}
                placeholder={values[field.key] === '***configured***' ? '(configured)' : field.required ? 'Required' : 'Optional'}
                className="flex-1 px-2.5 py-1.5 rounded text-xs transition-all duration-150 focus:outline-none"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono)',
                }}
              />
            </div>
          ))}
        </div>
      )}
      {provider.config_fields.length === 0 && (
        <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
          No credentials required
        </div>
      )}
    </div>
  )
}

// ─── Providers Tab Content ──────────────────────────────────────────────────

function ProvidersTab({
  values,
  onFieldChange,
  onSave,
}: {
  values: Record<string, string>
  onFieldChange: (key: string, value: string) => void
  onSave: (changed: Record<string, unknown>) => void
}) {
  const { data: providersData, isLoading: providersLoading } = useProviders()
  const { data: statsData } = useProviderStats()
  const testProviderMut = useTestProvider()
  const clearCacheMut = useClearProviderCache()
  const [testResults, setTestResults] = useState<Record<string, { healthy: boolean; message: string } | 'testing'>>({})
  const [localPriority, setLocalPriority] = useState<string[] | null>(null)

  const providers = providersData?.providers ?? []

  // Initialize local priority from provider data
  useEffect(() => {
    if (providers.length > 0 && localPriority === null) {
      setLocalPriority(providers.map((p) => p.name))
    }
  }, [providers, localPriority])

  const orderedProviders = localPriority
    ? localPriority
        .map((name) => providers.find((p) => p.name === name))
        .filter((p): p is ProviderInfo => p !== undefined)
    : providers

  const handleTest = (name: string) => {
    setTestResults((prev) => ({ ...prev, [name]: 'testing' }))
    testProviderMut.mutate(name, {
      onSuccess: (result) => {
        setTestResults((prev) => ({ ...prev, [name]: { healthy: result.healthy, message: result.message } }))
      },
      onError: () => {
        setTestResults((prev) => ({ ...prev, [name]: { healthy: false, message: 'Test failed' } }))
      },
    })
  }

  const handleToggle = (name: string, currentlyEnabled: boolean) => {
    // Build the new providers_enabled list
    const enabledSet = new Set(providers.filter((p) => p.enabled).map((p) => p.name))
    if (currentlyEnabled) {
      enabledSet.delete(name)
    } else {
      enabledSet.add(name)
    }

    // If all are enabled, send empty string (= all enabled by default)
    const allNames = providers.map((p) => p.name)
    const newValue = enabledSet.size === allNames.length ? '' : Array.from(enabledSet).join(',')
    onSave({ providers_enabled: newValue })
  }

  const handleMove = (index: number, direction: 'up' | 'down') => {
    if (!localPriority) return
    const newOrder = [...localPriority]
    const swapIdx = direction === 'up' ? index - 1 : index + 1
    if (swapIdx < 0 || swapIdx >= newOrder.length) return
    ;[newOrder[index], newOrder[swapIdx]] = [newOrder[swapIdx], newOrder[index]]
    setLocalPriority(newOrder)
    onSave({ provider_priorities: newOrder.join(',') })
  }

  const handleClearCache = (providerName?: string) => {
    clearCacheMut.mutate(providerName, {
      onSuccess: () => {
        toast(`Cache cleared${providerName ? ` for ${providerName}` : ''}`)
      },
    })
  }

  if (providersLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Global cache clear */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {orderedProviders.length} providers configured — drag priority with arrows
        </span>
        <button
          onClick={() => handleClearCache()}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all duration-150"
          style={{
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-primary)',
          }}
        >
          <Trash2 size={12} />
          Clear All Cache
        </button>
      </div>

      {orderedProviders.map((provider, idx) => {
        const cacheCount = statsData?.cache[provider.name]?.total ?? 0
        return (
          <ProviderCard
            key={provider.name}
            provider={provider}
            cacheCount={cacheCount}
            values={values}
            onFieldChange={onFieldChange}
            onTest={() => handleTest(provider.name)}
            testResult={testResults[provider.name]}
            onMoveUp={() => handleMove(idx, 'up')}
            onMoveDown={() => handleMove(idx, 'down')}
            isFirst={idx === 0}
            isLast={idx === orderedProviders.length - 1}
            onToggle={() => handleToggle(provider.name, provider.enabled)}
            onClearCache={() => handleClearCache(provider.name)}
          />
        )
      })}
    </div>
  )
}

// ─── Language Profiles Tab ──────────────────────────────────────────────────

function LanguageProfilesTab() {
  const { data: profiles, isLoading } = useLanguageProfiles()
  const createProfile = useCreateProfile()
  const updateProfile = useUpdateProfile()
  const deleteProfile = useDeleteProfile()
  const [editingId, setEditingId] = useState<number | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({
    name: '',
    source_language: 'en',
    source_language_name: 'English',
    target_languages: '',
    target_language_names: '',
  })

  const resetForm = () => {
    setForm({ name: '', source_language: 'en', source_language_name: 'English', target_languages: '', target_language_names: '' })
    setEditingId(null)
    setShowAdd(false)
  }

  const startEdit = (p: LanguageProfile) => {
    setForm({
      name: p.name,
      source_language: p.source_language,
      source_language_name: p.source_language_name,
      target_languages: p.target_languages.join(', '),
      target_language_names: p.target_language_names.join(', '),
    })
    setEditingId(p.id)
    setShowAdd(false)
  }

  const handleSave = () => {
    const targetLangs = form.target_languages.split(',').map((s) => s.trim()).filter(Boolean)
    const targetNames = form.target_language_names.split(',').map((s) => s.trim()).filter(Boolean)
    if (!form.name || targetLangs.length === 0) {
      toast('Name and at least one target language required', 'error')
      return
    }
    if (targetLangs.length !== targetNames.length) {
      toast('Target language codes and names must have the same count', 'error')
      return
    }

    const payload = {
      name: form.name,
      source_language: form.source_language,
      source_language_name: form.source_language_name,
      target_languages: targetLangs,
      target_language_names: targetNames,
    }

    if (editingId) {
      updateProfile.mutate({ id: editingId, data: payload }, {
        onSuccess: () => { toast('Profile updated'); resetForm() },
        onError: () => toast('Failed to update profile', 'error'),
      })
    } else {
      createProfile.mutate(payload, {
        onSuccess: () => { toast('Profile created'); resetForm() },
        onError: () => toast('Failed to create profile', 'error'),
      })
    }
  }

  const handleDelete = (id: number) => {
    deleteProfile.mutate(id, {
      onSuccess: () => toast('Profile deleted'),
      onError: () => toast('Cannot delete default profile', 'error'),
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          Language profiles define which languages to translate for each series/movie
        </span>
        <button
          onClick={() => { setShowAdd(true); setEditingId(null); setForm({ name: '', source_language: 'en', source_language_name: 'English', target_languages: '', target_language_names: '' }) }}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all duration-150"
          style={{ border: '1px solid var(--accent-dim)', color: 'var(--accent)', backgroundColor: 'var(--accent-bg)' }}
        >
          <Plus size={12} />
          Add Profile
        </button>
      </div>

      {/* Add/Edit Form */}
      {(showAdd || editingId !== null) && (
        <div
          className="rounded-lg p-4 space-y-3"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {editingId ? 'Edit Profile' : 'New Profile'}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Name</label>
              <input
                type="text" value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. German Only"
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Source Language Code</label>
              <input
                type="text" value={form.source_language}
                onChange={(e) => setForm((f) => ({ ...f, source_language: e.target.value }))}
                placeholder="en"
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Source Language Name</label>
              <input
                type="text" value={form.source_language_name}
                onChange={(e) => setForm((f) => ({ ...f, source_language_name: e.target.value }))}
                placeholder="English"
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Target Language Codes (comma-separated)</label>
              <input
                type="text" value={form.target_languages}
                onChange={(e) => setForm((f) => ({ ...f, target_languages: e.target.value }))}
                placeholder="de, fr"
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
              />
            </div>
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Target Language Names (comma-separated, same order)</label>
              <input
                type="text" value={form.target_language_names}
                onChange={(e) => setForm((f) => ({ ...f, target_language_names: e.target.value }))}
                placeholder="German, French"
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              />
            </div>
          </div>
          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={handleSave}
              disabled={createProfile.isPending || updateProfile.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {(createProfile.isPending || updateProfile.isPending) ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Check size={12} />
              )}
              Save
            </button>
            <button onClick={resetForm} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
              <X size={12} /> Cancel
            </button>
          </div>
        </div>
      )}

      {/* Profile List */}
      {(profiles || []).map((p) => (
        <div
          key={p.id}
          className="rounded-lg p-4 space-y-2"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Globe size={14} style={{ color: 'var(--accent)' }} />
              <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{p.name}</span>
              {p.is_default && (
                <span
                  className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                  style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
                >
                  Default
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => startEdit(p)}
                className="p-1.5 rounded transition-all duration-150"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
                title="Edit profile"
              >
                <Edit2 size={12} />
              </button>
              {!p.is_default && (
                <button
                  onClick={() => handleDelete(p.id)}
                  disabled={deleteProfile.isPending}
                  className="p-1.5 rounded transition-all duration-150"
                  style={{ border: '1px solid var(--border)', color: 'var(--error)', backgroundColor: 'var(--bg-primary)' }}
                  title="Delete profile"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--text-secondary)' }}>
            <span>Source: <code style={{ fontFamily: 'var(--font-mono)' }}>{p.source_language}</code> ({p.source_language_name})</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Targets:</span>
            {p.target_languages.map((lang, i) => (
              <span
                key={lang}
                className="px-2 py-0.5 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}
              >
                {lang.toUpperCase()} ({p.target_language_names[i]})
              </span>
            ))}
          </div>
        </div>
      ))}

      {(!profiles || profiles.length === 0) && !showAdd && (
        <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
          No language profiles configured. A default profile will be created automatically.
        </div>
      )}
    </div>
  )
}

// ─── Settings Page ──────────────────────────────────────────────────────────

export function SettingsPage() {
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()
  const [activeTab, setActiveTab] = useState('General')
  const [values, setValues] = useState<Record<string, string>>({})
  const [testResults, setTestResults] = useState<Record<string, string>>({})

  useEffect(() => {
    if (config) {
      const v: Record<string, string> = {}
      for (const key of Object.keys(config)) {
        v[key] = String(config[key] ?? '')
      }
      setValues(v)
    }
  }, [config])

  const handleSave = () => {
    const changed: Record<string, unknown> = {}
    for (const [key, val] of Object.entries(values)) {
      if (String(config?.[key] ?? '') !== val && val !== '***configured***') {
        changed[key] = val
      }
    }
    if (Object.keys(changed).length > 0) {
      doSave(changed)
    }
  }

  const doSave = (changed: Record<string, unknown>) => {
    updateConfig.mutate(changed, {
      onSuccess: () => {
        toast('Settings saved successfully')
      },
      onError: () => {
        toast('Failed to save settings', 'error')
      },
    })
  }

  const handleTestConnection = async (service: string) => {
    setTestResults((prev) => ({ ...prev, [service]: 'testing...' }))
    try {
      const health = await getHealth()
      const serviceKey = service.replace(' (Legacy)', '').toLowerCase()
      const status = health.services[serviceKey] || 'unknown'
      setTestResults((prev) => ({ ...prev, [service]: status }))
    } catch {
      setTestResults((prev) => ({ ...prev, [service]: 'error' }))
    }
  }

  const retranslateStatus = useRetranslateStatus()
  const retranslateBatch = useRetranslateBatch()

  const tabFields = FIELDS.filter((f) => f.tab === activeTab)
  const hasTestConnection = ['Ollama', 'Sonarr', 'Radarr', 'Jellyfin'].includes(activeTab)
  const isProvidersTab = activeTab === 'Providers'
  const isLanguagesTab = activeTab === 'Languages'
  const isTranslationTab = activeTab === 'Translation'

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1>Settings</h1>
        <button
          onClick={handleSave}
          disabled={updateConfig.isPending}
          className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-white hover:opacity-90"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {updateConfig.isPending ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Save size={14} />
              Save
            </>
          )}
        </button>
      </div>

      <div className="flex flex-col md:flex-row gap-5">
        {/* Tabs */}
        <div className="w-full md:w-40 shrink-0 flex flex-row md:flex-col gap-1 overflow-x-auto md:overflow-x-visible">
          {TABS.map((tab) => {
            const isActive = activeTab === tab
            return (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className="text-left px-3 py-2 rounded-md text-[13px] font-medium transition-all duration-150 whitespace-nowrap relative"
                style={{
                  backgroundColor: isActive ? 'var(--accent-bg)' : 'transparent',
                  color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                }}
                onMouseEnter={(e) => {
                  if (!isActive) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                }}
                onMouseLeave={(e) => {
                  if (!isActive) e.currentTarget.style.backgroundColor = 'transparent'
                }}
              >
                {isActive && (
                  <div
                    className="hidden md:block absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r-full"
                    style={{ backgroundColor: 'var(--accent)' }}
                  />
                )}
                {tab}
              </button>
            )
          })}
        </div>

        {/* Content */}
        <div className="flex-1">
          {isProvidersTab ? (
            <ProvidersTab
              values={values}
              onFieldChange={(key, value) => setValues((v) => ({ ...v, [key]: value }))}
              onSave={doSave}
            />
          ) : isLanguagesTab ? (
            <LanguageProfilesTab />
          ) : (
            <div
              className="rounded-lg p-5 space-y-4"
              style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
            >
              {tabFields.map((field) => (
                <div key={field.key} className="space-y-1.5">
                  <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {field.label}
                  </label>
                  <input
                    type={field.type}
                    value={values[field.key] === '***configured***' ? '' : (values[field.key] ?? '')}
                    onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
                    placeholder={values[field.key] === '***configured***' ? '(configured \u2014 enter new value to change)' : field.placeholder}
                    className="w-full px-3 py-2 rounded-md text-sm transition-all duration-150 focus:outline-none"
                    style={{
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border)',
                      color: 'var(--text-primary)',
                      fontFamily: field.type === 'text' ? 'var(--font-mono)' : undefined,
                      fontSize: '13px',
                    }}
                  />
                </div>
              ))}

              {hasTestConnection && (
                <div className="pt-3" style={{ borderTop: '1px solid var(--border)' }}>
                  <button
                    onClick={() => handleTestConnection(activeTab)}
                    className="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
                    style={{
                      border: '1px solid var(--border)',
                      color: 'var(--text-secondary)',
                      backgroundColor: 'var(--bg-primary)',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = 'var(--accent-dim)'
                      e.currentTarget.style.color = 'var(--accent)'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = 'var(--border)'
                      e.currentTarget.style.color = 'var(--text-secondary)'
                    }}
                  >
                    <TestTube size={14} />
                    Test Connection
                  </button>
                  {testResults[activeTab] && (
                    <div className="mt-2 text-sm">
                      Result:{' '}
                      <span
                        className="font-medium"
                        style={{
                          color: testResults[activeTab] === 'OK'
                            ? 'var(--success)'
                            : testResults[activeTab] === 'testing...'
                              ? 'var(--accent)'
                              : 'var(--error)',
                        }}
                      >
                        {testResults[activeTab]}
                      </span>
                    </div>
                  )}
                </div>
              )}

              {isTranslationTab && retranslateStatus.data && (
                <div className="pt-3 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
                  <div>
                    <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
                      Re-Translation
                    </h3>
                    <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
                      <span>
                        Config hash: <code style={{ fontFamily: 'var(--font-mono)' }}>{retranslateStatus.data.current_hash}</code>
                      </span>
                      <span>
                        Model: <code style={{ fontFamily: 'var(--font-mono)' }}>{retranslateStatus.data.ollama_model}</code>
                      </span>
                    </div>
                  </div>
                  {retranslateStatus.data.outdated_count > 0 ? (
                    <div className="flex items-center gap-3">
                      <span className="text-sm" style={{ color: 'var(--warning)' }}>
                        {retranslateStatus.data.outdated_count} files translated with old config
                      </span>
                      <button
                        onClick={() => retranslateBatch.mutate(undefined, {
                          onSuccess: () => toast('Re-translation started'),
                          onError: () => toast('Failed to start re-translation', 'error'),
                        })}
                        disabled={retranslateBatch.isPending}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white hover:opacity-90"
                        style={{ backgroundColor: 'var(--warning)' }}
                      >
                        {retranslateBatch.isPending ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <RefreshCw size={12} />
                        )}
                        Re-translate All
                      </button>
                    </div>
                  ) : (
                    <span className="text-xs" style={{ color: 'var(--success)' }}>
                      All translations are up to date
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
