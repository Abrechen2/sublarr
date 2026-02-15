import { useState, useEffect, useRef } from 'react'
import {
  useConfig, useUpdateConfig, useProviders, useTestProvider, useProviderStats,
  useClearProviderCache, useRetranslateStatus, useRetranslateBatch,
  useLanguageProfiles, useCreateProfile, useUpdateProfile, useDeleteProfile,
  useExportConfig, useImportConfig,
  usePromptPresets, useCreatePromptPreset, useUpdatePromptPreset, useDeletePromptPreset,
  useBackends, useTestBackend, useBackendConfig, useSaveBackendConfig, useBackendStats,
} from '@/hooks/useApi'
import { Save, Loader2, TestTube, ChevronUp, ChevronDown, Trash2, Download, Database, RefreshCw, Plus, Edit2, X, Check, Globe, Upload, FileDown, Activity, Eye, EyeOff } from 'lucide-react'
import { getHealth } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import type { ProviderInfo, LanguageProfile, TranslationBackendInfo, BackendStats, BackendHealthResult } from '@/lib/types'

const TABS = [
  'General',
  'Translation',
  'Translation Backends',
  'Languages',
  'Automation',
  'Wanted',
  'Providers',
  'Sonarr',
  'Radarr',
  'Jellyfin',
  'Notifications',
  'Prompt Presets',
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
  // Translation
  { key: 'source_language', label: 'Source Language Code', type: 'text', placeholder: 'en', tab: 'Translation' },
  { key: 'target_language', label: 'Target Language Code', type: 'text', placeholder: 'de', tab: 'Translation' },
  { key: 'source_language_name', label: 'Source Language Name', type: 'text', placeholder: 'English', tab: 'Translation' },
  { key: 'target_language_name', label: 'Target Language Name', type: 'text', placeholder: 'German', tab: 'Translation' },
  { key: 'hi_removal_enabled', label: 'Remove Hearing Impaired Tags', type: 'text', placeholder: 'false', tab: 'Translation' },
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
  { key: 'wanted_anime_only', label: 'Anime Only (Sonarr)', type: 'text', placeholder: 'true', tab: 'Wanted' },
  { key: 'wanted_anime_movies_only', label: 'Anime Movies Only (Radarr)', type: 'text', placeholder: 'false', tab: 'Wanted' },
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
  // Notifications
  { key: 'notify_on_download', label: 'Notify on Download', type: 'text', placeholder: 'true', tab: 'Notifications' },
  { key: 'notify_on_upgrade', label: 'Notify on Upgrade', type: 'text', placeholder: 'true', tab: 'Notifications' },
  { key: 'notify_on_batch_complete', label: 'Notify on Batch Complete', type: 'text', placeholder: 'true', tab: 'Notifications' },
  { key: 'notify_on_error', label: 'Notify on Error', type: 'text', placeholder: 'true', tab: 'Notifications' },
  { key: 'notify_manual_actions', label: 'Notify Manual Actions', type: 'text', placeholder: 'false', tab: 'Notifications' },
]

// ─── Path Mapping Editor ────────────────────────────────────────────────────

function PathMappingEditor({
  value,
  onChange,
}: {
  value: string
  onChange: (val: string) => void
}) {
  const [testPath, setTestPath] = useState('')
  const [testResult, setTestResult] = useState<{ mapped_path: string; exists: boolean } | null>(null)
  const [isTesting, setIsTesting] = useState(false)

  const handleTestPath = async () => {
    if (!testPath.trim()) return
    setIsTesting(true)
    try {
      const response = await fetch('/api/v1/settings/path-mapping/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ remote_path: testPath }),
      })
      const data = await response.json()
      if (response.ok) {
        setTestResult(data)
      } else {
        toast(data.error || 'Path mapping test failed', 'error')
        setTestResult(null)
      }
    } catch (error) {
      toast('Failed to test path mapping', 'error')
      setTestResult(null)
    } finally {
      setIsTesting(false)
    }
  }
  const parseRows = (val: string): { remote: string; local: string }[] => {
    if (!val || !val.trim()) return []
    return val.split(';').filter(Boolean).map((pair) => {
      const eqIdx = pair.indexOf('=')
      if (eqIdx === -1) return { remote: pair, local: '' }
      return { remote: pair.slice(0, eqIdx), local: pair.slice(eqIdx + 1) }
    })
  }

  const rows = parseRows(value)

  const serialize = (r: { remote: string; local: string }[]) =>
    r.filter((x) => x.remote || x.local).map((x) => `${x.remote}=${x.local}`).join(';')

  const updateRow = (index: number, field: 'remote' | 'local', newVal: string) => {
    const updated = [...rows]
    updated[index] = { ...updated[index], [field]: newVal }
    onChange(serialize(updated))
  }

  const removeRow = (index: number) => {
    onChange(serialize(rows.filter((_, i) => i !== index)))
  }

  const addRow = () => {
    onChange(value ? value + ';=' : '=')
  }

  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
        Path Mapping (Remote &rarr; Local)
      </label>
      <div className="space-y-2">
        {rows.length > 0 && (
          <div
            className="grid gap-2 text-xs font-medium"
            style={{ gridTemplateColumns: '1fr 1fr 2rem', color: 'var(--text-muted)' }}
          >
            <span>Remote Path</span>
            <span>Local Path</span>
            <span />
          </div>
        )}
        {rows.map((row, i) => (
          <div
            key={i}
            className="grid gap-2 items-center"
            style={{ gridTemplateColumns: '1fr 1fr 2rem' }}
          >
            <input
              type="text"
              value={row.remote}
              onChange={(e) => updateRow(i, 'remote', e.target.value)}
              placeholder="/data/media"
              className="px-3 py-2 rounded-md text-sm focus:outline-none"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
              }}
            />
            <input
              type="text"
              value={row.local}
              onChange={(e) => updateRow(i, 'local', e.target.value)}
              placeholder="Z:\Media"
              className="px-3 py-2 rounded-md text-sm focus:outline-none"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
              }}
            />
            <button
              onClick={() => removeRow(i)}
              className="p-1.5 rounded transition-all duration-150"
              style={{ color: 'var(--text-muted)' }}
              title="Remove mapping"
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <button
          onClick={addRow}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
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
          <Plus size={12} />
          Add Mapping
        </button>
      </div>
      {/* Test Path Mapping */}
      <div className="pt-3 space-y-2" style={{ borderTop: '1px solid var(--border)' }}>
        <label className="block text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          Test Path Mapping
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={testPath}
            onChange={(e) => setTestPath(e.target.value)}
            placeholder="/data/media/anime/Series.mkv"
            className="flex-1 px-3 py-2 rounded-md text-sm focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
              fontSize: '13px',
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleTestPath()
            }}
          />
          <button
            onClick={handleTestPath}
            disabled={isTesting || !testPath.trim()}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
            }}
            onMouseEnter={(e) => {
              if (!e.currentTarget.disabled) {
                e.currentTarget.style.borderColor = 'var(--accent-dim)'
                e.currentTarget.style.color = 'var(--accent)'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.color = 'var(--text-secondary)'
            }}
          >
            {isTesting ? <Loader2 size={14} className="animate-spin" /> : <TestTube size={14} />}
            Test
          </button>
        </div>
        {testResult && (
          <div className="text-xs space-y-1" style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Mapped to:</span>{' '}
              <span style={{ color: 'var(--accent)' }}>{testResult.mapped_path}</span>
            </div>
            <div>
              <span style={{ color: testResult.exists ? 'var(--success)' : 'var(--error)' }}>
                {testResult.exists ? '✓ File exists' : '✗ File not found'}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Instance Editor Component ──────────────────────────────────────────────

interface InstanceEntry {
  name: string
  url: string
  api_key: string
  path_mapping?: string
}

function InstanceEditor({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (val: string) => void
}) {
  const [instances, setInstances] = useState<InstanceEntry[]>(() => {
    try {
      const parsed = JSON.parse(value || '[]')
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  })

  const sync = (updated: InstanceEntry[]) => {
    setInstances(updated)
    onChange(updated.length > 0 ? JSON.stringify(updated) : '')
  }

  const addInstance = () => {
    sync([...instances, { name: '', url: '', api_key: '', path_mapping: '' }])
  }

  const removeInstance = (idx: number) => {
    sync(instances.filter((_, i) => i !== idx))
  }

  const updateField = (idx: number, field: keyof InstanceEntry, val: string) => {
    const updated = [...instances]
    updated[idx] = { ...updated[idx], [field]: val }
    sync(updated)
  }

  const inputStyle = {
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
  }

  return (
    <div className="pt-3 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {label} Instances
        </h3>
        <button
          onClick={addInstance}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all duration-150"
          style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
        >
          <Plus size={12} />
          Add Instance
        </button>
      </div>
      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
        Configure multiple {label} instances. If empty, the legacy URL/Key above is used.
      </p>
      {instances.map((inst, idx) => (
        <div
          key={idx}
          className="rounded-lg p-3 space-y-2"
          style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Instance {idx + 1}
            </span>
            <button
              onClick={() => removeInstance(idx)}
              className="p-1 rounded transition-colors"
              style={{ color: 'var(--text-muted)' }}
            >
              <Trash2 size={12} />
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input
              type="text"
              placeholder="Name (e.g. Main)"
              value={inst.name}
              onChange={(e) => updateField(idx, 'name', e.target.value)}
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={inputStyle}
            />
            <input
              type="text"
              placeholder="URL (e.g. http://localhost:8989)"
              value={inst.url}
              onChange={(e) => updateField(idx, 'url', e.target.value)}
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={inputStyle}
            />
            <input
              type="password"
              placeholder="API Key"
              value={inst.api_key}
              onChange={(e) => updateField(idx, 'api_key', e.target.value)}
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={inputStyle}
            />
            <input
              type="text"
              placeholder="Path Mapping (optional)"
              value={inst.path_mapping || ''}
              onChange={(e) => updateField(idx, 'path_mapping', e.target.value)}
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={inputStyle}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

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
  onReEnable,
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
  onReEnable: () => void
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

      {/* Health stats */}
      {provider.stats && (
        <div className="space-y-1.5">
          {/* Success rate bar */}
          <div className="flex items-center gap-2">
            <span className="text-xs w-8" style={{ color: 'var(--text-muted)' }}>
              {Math.round(provider.stats.success_rate * 100)}%
            </span>
            <div className="flex-1 h-1.5 rounded-full" style={{ backgroundColor: 'var(--bg-primary)' }}>
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${provider.stats.success_rate * 100}%`,
                  backgroundColor: provider.stats.success_rate > 0.8
                    ? 'rgb(16 185 129)'
                    : provider.stats.success_rate > 0.5
                      ? 'rgb(245 158 11)'
                      : 'rgb(239 68 68)',
                }}
              />
            </div>
          </div>

          {/* Response time and failure info */}
          <div className="flex items-center gap-3 flex-wrap text-xs" style={{ color: 'var(--text-muted)' }}>
            {provider.stats.avg_response_time_ms > 0 && (
              <span>Avg: {Math.round(provider.stats.avg_response_time_ms)}ms</span>
            )}
            {provider.stats.last_response_time_ms > 0 && (
              <span>Last: {Math.round(provider.stats.last_response_time_ms)}ms</span>
            )}
            {provider.stats.consecutive_failures > 0 && (
              <span style={{ color: 'rgb(245 158 11)' }}>
                {provider.stats.consecutive_failures} consecutive failures
              </span>
            )}
          </div>

          {/* Auto-disabled badge with re-enable button */}
          {provider.stats.auto_disabled && (
            <div className="flex items-center gap-2">
              <span
                className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--error-bg)', color: 'var(--error)' }}
              >
                Disabled until {provider.stats.disabled_until
                  ? new Date(provider.stats.disabled_until).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                  : 'unknown'}
              </span>
              <button
                onClick={onReEnable}
                className="px-2 py-0.5 rounded text-xs font-medium transition-all duration-150"
                style={{
                  border: '1px solid var(--accent-dim)',
                  color: 'var(--accent)',
                  backgroundColor: 'var(--accent-bg)',
                }}
              >
                Re-enable
              </button>
            </div>
          )}
        </div>
      )}

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

  const handleReEnable = (name: string) => {
    void (async () => {
      try {
        const { enableProvider } = await import('@/api/client')
        const result = await enableProvider(name)
        toast(result.message || `Provider ${name} re-enabled`)
      } catch {
        toast(`Failed to re-enable ${name}`, 'error')
      }
    })()
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
            onReEnable={() => handleReEnable(provider.name)}
          />
        )
      })}
    </div>
  )
}

// ─── Language Profiles Tab ──────────────────────────────────────────────────

// ─── Prompt Presets Tab ────────────────────────────────────────────────────────

function PromptPresetsTab() {
  const { data, isLoading } = usePromptPresets()
  const createPreset = useCreatePromptPreset()
  const updatePreset = useUpdatePromptPreset()
  const deletePreset = useDeletePromptPreset()
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [formData, setFormData] = useState({ name: '', prompt_template: '', is_default: false })

  const presets = data?.presets || []

  const resetForm = () => {
    setShowAdd(false)
    setEditingId(null)
    setFormData({ name: '', prompt_template: '', is_default: false })
  }

  const startEdit = (preset: { id: number; name: string; prompt_template: string; is_default: number }) => {
    setEditingId(preset.id)
    setFormData({
      name: preset.name,
      prompt_template: preset.prompt_template,
      is_default: preset.is_default === 1,
    })
    setShowAdd(false)
  }

  const handleSave = () => {
    if (!formData.name.trim() || !formData.prompt_template.trim()) {
      toast('Name and prompt template are required', 'error')
      return
    }

    if (editingId) {
      updatePreset.mutate(
        { presetId: editingId, ...formData },
        {
          onSuccess: () => {
            toast('Preset updated')
            resetForm()
          },
          onError: () => toast('Failed to update preset', 'error'),
        }
      )
    } else {
      createPreset.mutate(formData, {
        onSuccess: () => {
          toast('Preset created')
          resetForm()
        },
        onError: () => toast('Failed to create preset', 'error'),
      })
    }
  }

  const handleDelete = (id: number) => {
    if (!confirm('Delete this preset? You cannot delete the last preset.')) return
    deletePreset.mutate(id, {
      onSuccess: () => toast('Preset deleted'),
      onError: () => toast('Failed to delete preset', 'error'),
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
          Prompt Presets
        </h2>
        <button
          onClick={() => {
            resetForm()
            setShowAdd(true)
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          <Plus size={12} />
          Add Preset
        </button>
      </div>

      {showAdd && (
        <div
          className="rounded-lg p-4 space-y-3"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {editingId ? 'Edit Preset' : 'New Preset'}
          </div>
          <div className="space-y-2">
            <input
              type="text"
              placeholder="Preset name"
              value={formData.name}
              onChange={(e) => setFormData((f) => ({ ...f, name: e.target.value }))}
              className="w-full px-3 py-2 rounded-md text-sm"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
            <textarea
              placeholder="Prompt template..."
              value={formData.prompt_template}
              onChange={(e) => setFormData((f) => ({ ...f, prompt_template: e.target.value }))}
              rows={8}
              className="w-full px-3 py-2 rounded-md text-sm font-mono"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
              }}
            />
            <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
              <input
                type="checkbox"
                checked={formData.is_default}
                onChange={(e) => setFormData((f) => ({ ...f, is_default: e.target.checked }))}
              />
              Set as default
            </label>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={createPreset.isPending || updatePreset.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {(createPreset.isPending || updatePreset.isPending) ? (
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

      {presets.map((p) => (
        <div
          key={p.id}
          className="rounded-lg p-4 space-y-2"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{p.name}</span>
              {p.is_default === 1 && (
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
                title="Edit preset"
              >
                <Edit2 size={12} />
              </button>
              {presets.length > 1 && (
                <button
                  onClick={() => handleDelete(p.id)}
                  disabled={deletePreset.isPending}
                  className="p-1.5 rounded transition-all duration-150"
                  style={{ border: '1px solid var(--border)', color: 'var(--error)', backgroundColor: 'var(--bg-primary)' }}
                  title="Delete preset"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          </div>
          {editingId === p.id ? (
            <div className="space-y-2">
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData((f) => ({ ...f, name: e.target.value }))}
                className="w-full px-3 py-2 rounded-md text-sm"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                }}
              />
              <textarea
                value={formData.prompt_template}
                onChange={(e) => setFormData((f) => ({ ...f, prompt_template: e.target.value }))}
                rows={8}
                className="w-full px-3 py-2 rounded-md text-sm font-mono"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                }}
              />
              <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                <input
                  type="checkbox"
                  checked={formData.is_default}
                  onChange={(e) => setFormData((f) => ({ ...f, is_default: e.target.checked }))}
                />
                Set as default
              </label>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSave}
                  disabled={updatePreset.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
                  style={{ backgroundColor: 'var(--accent)' }}
                >
                  {updatePreset.isPending ? (
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
          ) : (
            <div
              className="rounded px-3 py-2 text-xs font-mono max-h-32 overflow-auto"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
                whiteSpace: 'pre-wrap',
              }}
            >
              {p.prompt_template}
            </div>
          )}
        </div>
      ))}

      {presets.length === 0 && !showAdd && (
        <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
          No prompt presets configured. A default preset will be created automatically.
        </div>
      )}
    </div>
  )
}

// ─── Translation Backend Card ────────────────────────────────────────────────

function BackendCard({
  backend,
  stats,
  onTest,
  testResult,
}: {
  backend: TranslationBackendInfo
  stats?: BackendStats
  onTest: () => void
  testResult?: BackendHealthResult | 'testing'
}) {
  const [expanded, setExpanded] = useState(false)
  const [formValues, setFormValues] = useState<Record<string, string>>({})
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})
  const { data: configData } = useBackendConfig(expanded ? backend.name : '')
  const saveConfigMut = useSaveBackendConfig()

  // Load config values when expanded
  useEffect(() => {
    if (configData) {
      setFormValues(configData)
    }
  }, [configData])

  const handleSave = () => {
    saveConfigMut.mutate(
      { name: backend.name, config: formValues },
      {
        onSuccess: () => toast('Backend config saved'),
        onError: () => toast('Failed to save backend config', 'error'),
      }
    )
  }

  const successRate = stats && stats.total_requests > 0
    ? Math.round((stats.successful_translations / stats.total_requests) * 100)
    : null

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
      }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between gap-3 p-4 text-left transition-colors"
        style={{ backgroundColor: expanded ? 'var(--bg-surface-hover)' : undefined }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {backend.display_name}
          </span>
          <span
            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium"
            style={{
              backgroundColor: backend.configured ? 'var(--success-bg)' : 'rgba(124,130,147,0.08)',
              color: backend.configured ? 'var(--success)' : 'var(--text-muted)',
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: backend.configured ? 'var(--success)' : 'var(--text-muted)' }}
            />
            {backend.configured ? 'Configured' : 'Not configured'}
          </span>
          {backend.supports_glossary && (
            <span
              className="px-1.5 py-0.5 rounded text-[10px] font-medium"
              style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
            >
              Glossary
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {successRate !== null && (
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {successRate}% success
            </span>
          )}
          {expanded ? <ChevronUp size={16} style={{ color: 'var(--text-muted)' }} /> : <ChevronDown size={16} style={{ color: 'var(--text-muted)' }} />}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4" style={{ borderTop: '1px solid var(--border)' }}>
          {/* Stats row */}
          {stats && stats.total_requests > 0 && (
            <div className="pt-3 space-y-2">
              <div className="flex items-center gap-2">
                <Activity size={12} style={{ color: 'var(--text-muted)' }} />
                <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  Statistics
                </span>
              </div>
              {/* Success rate bar */}
              <div className="flex items-center gap-2">
                <span className="text-xs w-8" style={{ color: 'var(--text-muted)' }}>
                  {successRate}%
                </span>
                <div className="flex-1 h-1.5 rounded-full" style={{ backgroundColor: 'var(--bg-primary)' }}>
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${successRate}%`,
                      backgroundColor: (successRate ?? 0) > 80
                        ? 'rgb(16 185 129)'
                        : (successRate ?? 0) > 50
                          ? 'rgb(245 158 11)'
                          : 'rgb(239 68 68)',
                    }}
                  />
                </div>
              </div>
              <div className="flex items-center gap-3 flex-wrap text-xs" style={{ color: 'var(--text-muted)' }}>
                <span>{stats.successful_translations}/{stats.total_requests} requests</span>
                {stats.avg_response_time_ms > 0 && (
                  <span>Avg: {Math.round(stats.avg_response_time_ms)}ms</span>
                )}
                {stats.last_response_time_ms > 0 && (
                  <span>Last: {Math.round(stats.last_response_time_ms)}ms</span>
                )}
                {stats.total_characters > 0 && (
                  <span>{stats.total_characters.toLocaleString()} chars</span>
                )}
                {stats.consecutive_failures > 0 && (
                  <span style={{ color: 'rgb(245 158 11)' }}>
                    {stats.consecutive_failures} consecutive failures
                  </span>
                )}
              </div>
              {stats.last_error && (
                <div className="text-xs truncate" style={{ color: 'var(--error)' }} title={stats.last_error}>
                  Last error: {stats.last_error}
                </div>
              )}
            </div>
          )}

          {/* Config form */}
          {backend.config_fields.length > 0 && (
            <div className="space-y-3 pt-2" style={{ borderTop: stats && stats.total_requests > 0 ? '1px solid var(--border)' : undefined }}>
              {backend.config_fields.map((field) => (
                <div key={field.key} className="space-y-1">
                  <label className="flex items-center gap-1 text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                    {field.label}
                    {field.required && <span style={{ color: 'var(--error)' }}>*</span>}
                  </label>
                  <div className="flex items-center gap-1.5">
                    <input
                      type={field.type === 'password' && !showPasswords[field.key] ? 'password' : field.type === 'number' ? 'number' : 'text'}
                      value={formValues[field.key] === '***configured***' ? '' : (formValues[field.key] ?? field.default ?? '')}
                      onChange={(e) => setFormValues((v) => ({ ...v, [field.key]: e.target.value }))}
                      placeholder={formValues[field.key] === '***configured***' ? '(configured)' : field.default || (field.required ? 'Required' : 'Optional')}
                      className="flex-1 px-2.5 py-1.5 rounded text-xs transition-all duration-150 focus:outline-none"
                      style={{
                        backgroundColor: 'var(--bg-primary)',
                        border: '1px solid var(--border)',
                        color: 'var(--text-primary)',
                        fontFamily: 'var(--font-mono)',
                      }}
                    />
                    {field.type === 'password' && (
                      <button
                        onClick={() => setShowPasswords((p) => ({ ...p, [field.key]: !p[field.key] }))}
                        className="p-1.5 rounded transition-all duration-150"
                        style={{ border: '1px solid var(--border)', color: 'var(--text-muted)', backgroundColor: 'var(--bg-primary)' }}
                        title={showPasswords[field.key] ? 'Hide' : 'Show'}
                      >
                        {showPasswords[field.key] ? <EyeOff size={12} /> : <Eye size={12} />}
                      </button>
                    )}
                  </div>
                  {field.help && (
                    <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{field.help}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {backend.config_fields.length === 0 && (
            <div className="pt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
              No configuration required for this backend.
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-2 pt-2" style={{ borderTop: '1px solid var(--border)' }}>
            <button
              onClick={onTest}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150"
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
              {testResult === 'testing' ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <TestTube size={12} />
              )}
              Test
            </button>

            {backend.config_fields.length > 0 && (
              <button
                onClick={handleSave}
                disabled={saveConfigMut.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {saveConfigMut.isPending ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Save size={12} />
                )}
                Save
              </button>
            )}

            {/* Test result inline */}
            {testResult && testResult !== 'testing' && (
              <span className="text-xs" style={{ color: testResult.healthy ? 'var(--success)' : 'var(--error)' }}>
                {testResult.healthy ? 'Healthy' : 'Error'}: {testResult.message}
              </span>
            )}
          </div>

          {/* Backend info */}
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            Max batch size: {backend.max_batch_size} lines
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Translation Backends Tab ────────────────────────────────────────────────

function TranslationBackendsTab() {
  const { data: backendsData, isLoading: backendsLoading } = useBackends()
  const { data: statsData } = useBackendStats()
  const testBackendMut = useTestBackend()
  const [testResults, setTestResults] = useState<Record<string, BackendHealthResult | 'testing'>>({})

  const backends = backendsData?.backends ?? []
  const statsMap = new Map<string, BackendStats>()
  if (statsData?.stats) {
    for (const s of statsData.stats) {
      statsMap.set(s.backend_name, s)
    }
  }

  const handleTest = (name: string) => {
    setTestResults((prev) => ({ ...prev, [name]: 'testing' }))
    testBackendMut.mutate(name, {
      onSuccess: (result) => {
        setTestResults((prev) => ({ ...prev, [name]: result }))
        if (result.healthy) {
          toast(`${name}: healthy`)
        } else {
          toast(`${name}: ${result.message}`, 'error')
        }
      },
      onError: () => {
        setTestResults((prev) => ({ ...prev, [name]: { healthy: false, message: 'Test request failed' } }))
        toast(`${name}: test failed`, 'error')
      },
    })
  }

  if (backendsLoading) {
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
          {backends.length} translation backends available &mdash; expand to configure and test
        </span>
      </div>

      {backends.map((backend) => (
        <BackendCard
          key={backend.name}
          backend={backend}
          stats={statsMap.get(backend.name)}
          onTest={() => handleTest(backend.name)}
          testResult={testResults[backend.name]}
        />
      ))}

      {backends.length === 0 && (
        <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
          No translation backends registered. Install backend packages (e.g. deepl, openai, google-cloud-translate) to enable them.
        </div>
      )}
    </div>
  )
}

// ─── Language Profiles Tab ────────────────────────────────────────────────────

function LanguageProfilesTab() {
  const { data: profiles, isLoading } = useLanguageProfiles()
  const { data: backendsData } = useBackends()
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
    translation_backend: '',
    fallback_chain: [] as string[],
  })

  const backends = backendsData?.backends ?? []

  const resetForm = () => {
    setForm({ name: '', source_language: 'en', source_language_name: 'English', target_languages: '', target_language_names: '', translation_backend: '', fallback_chain: [] })
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
      translation_backend: p.translation_backend || '',
      fallback_chain: p.fallback_chain || [],
    })
    setEditingId(p.id)
    setShowAdd(false)
  }

  const handleFallbackMove = (index: number, direction: 'up' | 'down') => {
    const chain = [...form.fallback_chain]
    const swapIdx = direction === 'up' ? index - 1 : index + 1
    if (swapIdx < 0 || swapIdx >= chain.length) return
    ;[chain[index], chain[swapIdx]] = [chain[swapIdx], chain[index]]
    setForm((f) => ({ ...f, fallback_chain: chain }))
  }

  const handleFallbackRemove = (index: number) => {
    setForm((f) => ({ ...f, fallback_chain: f.fallback_chain.filter((_, i) => i !== index) }))
  }

  const handleFallbackAdd = (name: string) => {
    if (!name || form.fallback_chain.includes(name)) return
    setForm((f) => ({ ...f, fallback_chain: [...f.fallback_chain, name] }))
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
      translation_backend: form.translation_backend || '',
      fallback_chain: form.fallback_chain,
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
          onClick={() => { setShowAdd(true); setEditingId(null); setForm({ name: '', source_language: 'en', source_language_name: 'English', target_languages: '', target_language_names: '', translation_backend: '', fallback_chain: [] }) }}
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

            {/* Translation Backend Selector */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Translation Backend</label>
              <select
                value={form.translation_backend}
                onChange={(e) => setForm((f) => ({ ...f, translation_backend: e.target.value }))}
                className="w-full px-2.5 py-1.5 rounded text-xs"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="">Default (Ollama)</option>
                {backends.map((b) => (
                  <option key={b.name} value={b.name}>{b.display_name}</option>
                ))}
              </select>
            </div>

            {/* Fallback Chain Editor */}
            <div className="space-y-1">
              <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Fallback Chain</label>
              <div className="space-y-1.5">
                {form.fallback_chain.length > 0 ? (
                  form.fallback_chain.map((name, idx) => {
                    const isPrimary = name === form.translation_backend
                    return (
                      <div key={name} className="flex items-center gap-1.5">
                        <span
                          className="flex-1 px-2 py-1 rounded text-xs"
                          style={{
                            backgroundColor: 'var(--bg-primary)',
                            border: '1px solid var(--border)',
                            color: isPrimary ? 'var(--accent)' : 'var(--text-primary)',
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          {idx + 1}. {backends.find((b) => b.name === name)?.display_name || name}
                          {isPrimary && ' (primary)'}
                        </span>
                        <button
                          onClick={() => handleFallbackMove(idx, 'up')}
                          disabled={idx === 0}
                          className="p-1 rounded"
                          style={{ color: idx === 0 ? 'var(--text-muted)' : 'var(--text-secondary)', border: '1px solid var(--border)', backgroundColor: 'var(--bg-primary)' }}
                        >
                          <ChevronUp size={10} />
                        </button>
                        <button
                          onClick={() => handleFallbackMove(idx, 'down')}
                          disabled={idx === form.fallback_chain.length - 1}
                          className="p-1 rounded"
                          style={{ color: idx === form.fallback_chain.length - 1 ? 'var(--text-muted)' : 'var(--text-secondary)', border: '1px solid var(--border)', backgroundColor: 'var(--bg-primary)' }}
                        >
                          <ChevronDown size={10} />
                        </button>
                        {!isPrimary && (
                          <button
                            onClick={() => handleFallbackRemove(idx)}
                            className="p-1 rounded"
                            style={{ color: 'var(--error)', border: '1px solid var(--border)', backgroundColor: 'var(--bg-primary)' }}
                          >
                            <X size={10} />
                          </button>
                        )}
                      </div>
                    )
                  })
                ) : (
                  <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                    No fallback chain configured. Add backends below.
                  </span>
                )}
                {/* Add backend to chain */}
                {backends.filter((b) => !form.fallback_chain.includes(b.name)).length > 0 && (
                  <select
                    value=""
                    onChange={(e) => { handleFallbackAdd(e.target.value); e.target.value = '' }}
                    className="w-full px-2.5 py-1 rounded text-xs"
                    style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}
                  >
                    <option value="">+ Add backend to fallback chain...</option>
                    {backends
                      .filter((b) => !form.fallback_chain.includes(b.name))
                      .map((b) => (
                        <option key={b.name} value={b.name}>{b.display_name}</option>
                      ))}
                  </select>
                )}
              </div>
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
          {/* Translation backend info */}
          <div className="flex items-center gap-4 flex-wrap text-xs" style={{ color: 'var(--text-secondary)' }}>
            {p.translation_backend && (
              <span>
                Backend: <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{p.translation_backend}</code>
              </span>
            )}
            {p.fallback_chain && p.fallback_chain.length > 0 && (
              <span>
                Fallback: <code style={{ fontFamily: 'var(--font-mono)' }}>{p.fallback_chain.join(' > ')}</code>
              </span>
            )}
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
  const exportConfig = useExportConfig()
  const importConfig = useImportConfig()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importPreview, setImportPreview] = useState<Record<string, unknown> | null>(null)

  const handleExport = () => {
    exportConfig.mutate(undefined, {
      onSuccess: (data) => {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `sublarr-config-${new Date().toISOString().slice(0, 10)}.json`
        a.click()
        URL.revokeObjectURL(url)
        toast('Config exported')
      },
      onError: () => toast('Export failed', 'error'),
    })
  }

  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(ev.target?.result as string)
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          toast('Invalid config file: expected JSON object', 'error')
          return
        }
        setImportPreview(parsed)
      } catch {
        toast('Invalid JSON file', 'error')
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const handleImportConfirm = () => {
    if (!importPreview) return
    importConfig.mutate(importPreview, {
      onSuccess: (result) => {
        setImportPreview(null)
        toast(`Imported ${result.imported_keys.length} settings` +
          (result.skipped_secrets.length > 0 ? ` (${result.skipped_secrets.length} secrets skipped)` : ''))
      },
      onError: () => toast('Import failed', 'error'),
    })
  }

  const tabFields = FIELDS.filter((f) => f.tab === activeTab)
  const hasTestConnection = ['Sonarr', 'Radarr', 'Jellyfin'].includes(activeTab)
  const isProvidersTab = activeTab === 'Providers'
  const isLanguagesTab = activeTab === 'Languages'
  const isTranslationTab = activeTab === 'Translation'
  const isPromptPresetsTab = activeTab === 'Prompt Presets'
  const isTranslationBackendsTab = activeTab === 'Translation Backends'

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
          ) : isPromptPresetsTab ? (
            <PromptPresetsTab />
          ) : isTranslationBackendsTab ? (
            <TranslationBackendsTab />
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

              {/* Path Mapping Table (General tab only) */}
              {activeTab === 'General' && (
                <PathMappingEditor
                  value={values.path_mapping ?? ''}
                  onChange={(val) => setValues((v) => ({ ...v, path_mapping: val }))}
                />
              )}

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

              {activeTab === 'Notifications' && (
                <div className="pt-3 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
                  <div className="space-y-1.5">
                    <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      Notification URLs (Apprise)
                    </label>
                    <textarea
                      value={values.notification_urls_json ?? ''}
                      onChange={(e) => setValues((v) => ({ ...v, notification_urls_json: e.target.value }))}
                      placeholder={'One URL per line, e.g.:\npushover://user@token\ndiscord://webhook_id/webhook_token\ntgram://bot_token/chat_id'}
                      rows={4}
                      className="w-full px-3 py-2 rounded-md text-sm transition-all duration-150 focus:outline-none resize-y"
                      style={{
                        backgroundColor: 'var(--bg-primary)',
                        border: '1px solid var(--border)',
                        color: 'var(--text-primary)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '13px',
                      }}
                    />
                    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      Supports Pushover, Discord, Telegram, Gotify, Email, and many more.{' '}
                      <a
                        href="https://github.com/caronc/apprise/wiki"
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: 'var(--accent)' }}
                      >
                        See Apprise docs
                      </a>
                    </p>
                  </div>
                  <button
                    onClick={async () => {
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
                    }}
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
                    Send Test Notification
                  </button>
                </div>
              )}

              {activeTab === 'Sonarr' && (
                <InstanceEditor
                  label="Sonarr"
                  value={values.sonarr_instances_json ?? ''}
                  onChange={(val) => setValues((v) => ({ ...v, sonarr_instances_json: val }))}
                />
              )}

              {activeTab === 'Radarr' && (
                <InstanceEditor
                  label="Radarr"
                  value={values.radarr_instances_json ?? ''}
                  onChange={(val) => setValues((v) => ({ ...v, radarr_instances_json: val }))}
                />
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

              {/* Config Export/Import (General tab only) */}
              {activeTab === 'General' && (
                <div className="pt-3 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
                  <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                    Config Backup
                  </h3>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      onClick={handleExport}
                      disabled={exportConfig.isPending}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
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
                      {exportConfig.isPending ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <FileDown size={14} />
                      )}
                      Export Config
                    </button>
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
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
                      <Upload size={14} />
                      Import Config
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".json"
                      onChange={handleImportFile}
                      className="hidden"
                    />
                  </div>
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    API keys and secrets are excluded from export/import for security.
                  </div>

                  {/* Import Preview Modal */}
                  {importPreview && (
                    <div
                      className="rounded-lg p-4 space-y-3"
                      style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--accent-dim)' }}
                    >
                      <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                        Import Preview
                      </div>
                      <div
                        className="max-h-48 overflow-auto rounded px-3 py-2 text-xs"
                        style={{
                          backgroundColor: 'var(--bg-surface)',
                          border: '1px solid var(--border)',
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--text-secondary)',
                        }}
                      >
                        {Object.entries(importPreview).map(([key, val]) => (
                          <div key={key} className="py-0.5">
                            <span style={{ color: 'var(--accent)' }}>{key}</span>
                            <span style={{ color: 'var(--text-muted)' }}>{': '}</span>
                            <span>{typeof val === 'string' ? val : JSON.stringify(val)}</span>
                          </div>
                        ))}
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleImportConfirm}
                          disabled={importConfig.isPending}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
                          style={{ backgroundColor: 'var(--accent)' }}
                        >
                          {importConfig.isPending ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <Check size={12} />
                          )}
                          Confirm Import
                        </button>
                        <button
                          onClick={() => setImportPreview(null)}
                          className="flex items-center gap-1 px-3 py-1.5 rounded text-xs"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          <X size={12} />
                          Cancel
                        </button>
                      </div>
                    </div>
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
