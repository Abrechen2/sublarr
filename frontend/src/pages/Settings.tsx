import { useState, useEffect } from 'react'
import { useConfig, useUpdateConfig, useProviders, useTestProvider, useProviderStats, useClearProviderCache } from '@/hooks/useApi'
import { Save, Loader2, TestTube, ChevronUp, ChevronDown, Trash2, Download, Database } from 'lucide-react'
import { getHealth } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import type { ProviderInfo } from '@/lib/types'

const TABS = [
  'General',
  'Ollama',
  'Translation',
  'Wanted',
  'Providers',
  'Bazarr (Legacy)',
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
  { key: 'webhook_delay_minutes', label: 'Webhook Delay (minutes)', type: 'number', placeholder: '5', tab: 'General' },
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
  // Wanted
  { key: 'wanted_scan_interval_hours', label: 'Scan Interval (hours, 0=disabled)', type: 'number', placeholder: '6', tab: 'Wanted' },
  { key: 'wanted_anime_only', label: 'Anime Only', type: 'text', placeholder: 'true', tab: 'Wanted' },
  { key: 'wanted_scan_on_startup', label: 'Scan on Startup', type: 'text', placeholder: 'true', tab: 'Wanted' },
  { key: 'wanted_max_search_attempts', label: 'Max Search Attempts', type: 'number', placeholder: '3', tab: 'Wanted' },
  // Bazarr (Legacy)
  { key: 'bazarr_url', label: 'Bazarr URL', type: 'text', placeholder: 'http://localhost:6767', tab: 'Bazarr (Legacy)' },
  { key: 'bazarr_api_key', label: 'Bazarr API Key', type: 'password', tab: 'Bazarr (Legacy)' },
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

  const tabFields = FIELDS.filter((f) => f.tab === activeTab)
  const hasTestConnection = ['Ollama', 'Bazarr (Legacy)', 'Sonarr', 'Radarr', 'Jellyfin'].includes(activeTab)
  const isProvidersTab = activeTab === 'Providers'

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
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
