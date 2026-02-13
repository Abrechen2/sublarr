import { useState, useEffect } from 'react'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { Save, CheckCircle2, Loader2, TestTube } from 'lucide-react'
import { getHealth } from '@/api/client'

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
  { key: 'path_mapping', label: 'Path Mapping (Remote→Local)', type: 'text', placeholder: '/data/media=Z:\\Media', tab: 'General' },
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
  const [saved, setSaved] = useState(false)
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
          setSaved(true)
          setTimeout(() => setSaved(false), 3000)
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
        <Loader2 size={32} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Settings</h1>
        <button
          onClick={handleSave}
          disabled={updateConfig.isPending}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white transition-all duration-200 hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ backgroundColor: saved ? 'var(--success)' : 'var(--accent)' }}
        >
          {saved ? (
            <>
              <CheckCircle2 size={16} />
              Saved!
            </>
          ) : updateConfig.isPending ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Save size={16} />
              Save
            </>
          )}
        </button>
      </div>

      <div className="flex flex-col md:flex-row gap-6">
        {/* Tabs */}
        <div className="w-full md:w-40 flex-shrink-0 flex flex-row md:flex-col gap-1 overflow-x-auto md:overflow-x-visible">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className="w-full md:w-full text-left px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 hover:bg-opacity-10 whitespace-nowrap"
              style={{
                backgroundColor: activeTab === tab ? 'rgba(29, 184, 212, 0.15)' : 'transparent',
                color: activeTab === tab ? 'var(--accent)' : 'var(--text-secondary)',
              }}
              onMouseEnter={(e) => {
                if (activeTab !== tab) {
                  e.currentTarget.style.backgroundColor = 'rgba(29, 184, 212, 0.05)'
                }
              }}
              onMouseLeave={(e) => {
                if (activeTab !== tab) {
                  e.currentTarget.style.backgroundColor = 'transparent'
                }
              }}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Fields */}
        <div className="flex-1">
          <div
            className="rounded-xl p-6 space-y-5 shadow-sm"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            {tabFields.map((field) => (
              <div key={field.key} className="space-y-1.5">
                <label className="block text-sm font-medium whitespace-nowrap" style={{ color: 'var(--text-primary)' }}>
                  {field.label}
                </label>
                <input
                  type={field.type}
                  value={values[field.key] === '***configured***' ? '' : (values[field.key] ?? '')}
                  onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
                  placeholder={values[field.key] === '***configured***' ? '(configured — enter new value to change)' : field.placeholder}
                  className="w-full px-3 py-2.5 rounded-lg text-sm transition-all duration-200 focus:outline-none"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)',
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'var(--accent)'
                    e.target.style.boxShadow = '0 0 0 2px rgba(29, 184, 212, 0.1)'
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'var(--border)'
                    e.target.style.boxShadow = 'none'
                  }}
                />
              </div>
            ))}

            {hasTestConnection && (
              <div className="pt-3" style={{ borderTop: '1px solid var(--border)' }}>
                <button
                  onClick={() => handleTestConnection(activeTab)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 hover:shadow-sm"
                  style={{ 
                    border: '1px solid var(--border)', 
                    color: 'var(--text-primary)',
                    backgroundColor: 'var(--bg-primary)',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = 'var(--accent)'
                    e.currentTarget.style.backgroundColor = 'rgba(29, 184, 212, 0.05)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'var(--border)'
                    e.currentTarget.style.backgroundColor = 'var(--bg-primary)'
                  }}
                >
                  <TestTube size={16} />
                  Test Connection
                </button>
                {testResults[activeTab] && (
                  <div className="mt-2 text-sm">
                    Result:{' '}
                    <span style={{
                      color: testResults[activeTab] === 'OK'
                        ? 'var(--success)'
                        : testResults[activeTab] === 'testing...'
                          ? 'var(--accent)'
                          : 'var(--error)',
                    }}>
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
