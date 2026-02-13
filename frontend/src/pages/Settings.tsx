import { useState, useEffect } from 'react'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { Save, Loader2, TestTube } from 'lucide-react'
import { getHealth } from '@/api/client'
import { toast } from '@/components/shared/Toast'

const TABS = [
  'General',
  'Ollama',
  'Translation',
  'Bazarr',
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
  // Bazarr
  { key: 'bazarr_url', label: 'Bazarr URL', type: 'text', placeholder: 'http://localhost:6767', tab: 'Bazarr' },
  { key: 'bazarr_api_key', label: 'Bazarr API Key', type: 'password', tab: 'Bazarr' },
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
      updateConfig.mutate(changed, {
        onSuccess: () => {
          toast('Settings saved successfully')
        },
        onError: () => {
          toast('Failed to save settings', 'error')
        },
      })
    }
  }

  const handleTestConnection = async (service: string) => {
    setTestResults((prev) => ({ ...prev, [service]: 'testing...' }))
    try {
      const health = await getHealth()
      const status = health.services[service.toLowerCase()] || 'unknown'
      setTestResults((prev) => ({ ...prev, [service]: status }))
    } catch {
      setTestResults((prev) => ({ ...prev, [service]: 'error' }))
    }
  }

  const tabFields = FIELDS.filter((f) => f.tab === activeTab)
  const hasTestConnection = ['Ollama', 'Bazarr', 'Sonarr', 'Radarr', 'Jellyfin'].includes(activeTab)

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
        <div className="w-full md:w-36 shrink-0 flex flex-row md:flex-col gap-1 overflow-x-auto md:overflow-x-visible">
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

        {/* Fields */}
        <div className="flex-1">
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
        </div>
      </div>
    </div>
  )
}
