import { useState, useEffect } from 'react'
import {
  useWhisperBackends, useTestWhisperBackend, useWhisperBackendConfig, useSaveWhisperBackendConfig,
  useWhisperConfig, useSaveWhisperConfig, useWhisperStats,
} from '@/hooks/useApi'
import { Save, Loader2, TestTube, ChevronUp, ChevronDown, Activity, Eye, EyeOff } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import type { WhisperBackendInfo, WhisperConfig, WhisperHealthResult, WhisperStats } from '@/lib/types'

const WHISPER_MODEL_INFO = [
  { model: 'tiny', size: '~150MB' },
  { model: 'base', size: '~300MB' },
  { model: 'small', size: '~900MB' },
  { model: 'medium', size: '~3GB' },
  { model: 'large-v2', size: '~6GB' },
  { model: 'large-v3', size: '~6GB' },
  { model: 'distil-large-v3', size: '~1.5GB' },
]

function WhisperBackendCard({
  backend,
  onTest,
  testResult,
}: {
  backend: WhisperBackendInfo
  onTest: () => void
  testResult?: WhisperHealthResult | 'testing'
}) {
  const [expanded, setExpanded] = useState(false)
  const [formValues, setFormValues] = useState<Record<string, string>>({})
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})
  const { data: configData } = useWhisperBackendConfig(expanded ? backend.name : '')
  const saveConfigMut = useSaveWhisperBackendConfig()

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
        onSuccess: () => toast('Whisper backend config saved'),
        onError: () => toast('Failed to save whisper backend config', 'error'),
      }
    )
  }

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
          {backend.supports_gpu && (
            <span
              className="px-1.5 py-0.5 rounded text-[10px] font-medium"
              style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
            >
              GPU
            </span>
          )}
          {backend.supports_language_detection && (
            <span
              className="px-1.5 py-0.5 rounded text-[10px] font-medium"
              style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
            >
              Language Detection
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {expanded ? <ChevronUp size={16} style={{ color: 'var(--text-muted)' }} /> : <ChevronDown size={16} style={{ color: 'var(--text-muted)' }} />}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4" style={{ borderTop: '1px solid var(--border)' }}>
          {/* Config form */}
          {backend.config_fields.length > 0 && (
            <div className="space-y-3 pt-3">
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

          {/* Model info for faster_whisper */}
          {backend.name === 'faster_whisper' && (
            <div className="space-y-2 pt-2" style={{ borderTop: '1px solid var(--border)' }}>
              <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                Available Models
              </span>
              <div className="rounded overflow-hidden text-xs" style={{ border: '1px solid var(--border)' }}>
                <table className="w-full">
                  <thead>
                    <tr style={{ backgroundColor: 'var(--bg-primary)' }}>
                      <th className="text-left px-3 py-1.5 font-medium" style={{ color: 'var(--text-secondary)' }}>Model</th>
                      <th className="text-left px-3 py-1.5 font-medium" style={{ color: 'var(--text-secondary)' }}>Approx Size</th>
                    </tr>
                  </thead>
                  <tbody>
                    {WHISPER_MODEL_INFO.map((m) => (
                      <tr key={m.model} style={{ borderTop: '1px solid var(--border)' }}>
                        <td className="px-3 py-1.5" style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{m.model}</td>
                        <td className="px-3 py-1.5" style={{ color: 'var(--text-muted)' }}>{m.size}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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
        </div>
      )}
    </div>
  )
}

export function WhisperTab() {
  const { data: backendsData, isLoading: backendsLoading } = useWhisperBackends()
  const { data: statsData } = useWhisperStats()
  const { data: whisperConfig, isLoading: configLoading } = useWhisperConfig()
  const saveConfigMut = useSaveWhisperConfig()
  const testBackendMut = useTestWhisperBackend()

  const [testResults, setTestResults] = useState<Record<string, WhisperHealthResult | 'testing'>>({})
  const [localConfig, setLocalConfig] = useState<WhisperConfig>({
    whisper_enabled: false,
    whisper_backend: '',
    max_concurrent_whisper: 1,
    whisper_fallback_min_score: 0,
  })

  const backends: WhisperBackendInfo[] = backendsData?.backends ?? []
  const stats: WhisperStats | undefined = statsData

  // Sync config from server
  useEffect(() => {
    if (whisperConfig) {
      setLocalConfig({
        whisper_enabled: whisperConfig.whisper_enabled ?? false,
        whisper_backend: whisperConfig.whisper_backend ?? '',
        max_concurrent_whisper: whisperConfig.max_concurrent_whisper ?? 1,
        whisper_fallback_min_score: whisperConfig.whisper_fallback_min_score ?? 0,
      })
    }
  }, [whisperConfig])

  const handleSaveConfig = () => {
    saveConfigMut.mutate(localConfig as unknown as Record<string, unknown>, {
      onSuccess: () => toast('Whisper config saved'),
      onError: () => toast('Failed to save whisper config', 'error'),
    })
  }

  const handleTest = (name: string) => {
    setTestResults((prev) => ({ ...prev, [name]: 'testing' }))
    testBackendMut.mutate(name, {
      onSuccess: (result: WhisperHealthResult) => {
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

  if (backendsLoading || configLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Global Whisper Config */}
      <div
        className="rounded-lg p-5 space-y-4"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          Whisper Configuration
        </h3>

        {/* Enable/disable toggle */}
        <div className="flex items-center justify-between">
          <div>
            <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
              Enable Whisper
            </label>
            <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
              Enable speech-to-text transcription as fallback when no subtitle providers have results
            </p>
          </div>
          <button
            onClick={() => setLocalConfig((c) => ({ ...c, whisper_enabled: !c.whisper_enabled }))}
            className="relative w-10 h-5 rounded-full transition-colors duration-200"
            style={{
              backgroundColor: localConfig.whisper_enabled ? 'var(--accent)' : 'var(--border)',
            }}
          >
            <span
              className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200"
              style={{
                transform: localConfig.whisper_enabled ? 'translateX(22px)' : 'translateX(2px)',
              }}
            />
          </button>
        </div>

        {/* Backend selection */}
        <div className="space-y-1">
          <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
            Active Backend
          </label>
          <select
            value={localConfig.whisper_backend}
            onChange={(e) => setLocalConfig((c) => ({ ...c, whisper_backend: e.target.value }))}
            className="w-full px-2.5 py-1.5 rounded text-xs transition-all duration-150 focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          >
            <option value="">Select backend...</option>
            {backends.map((b) => (
              <option key={b.name} value={b.name}>{b.display_name}</option>
            ))}
          </select>
        </div>

        {/* Max concurrent */}
        <div className="space-y-1">
          <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
            Max Concurrent Jobs
          </label>
          <input
            type="number"
            min={1}
            max={4}
            value={localConfig.max_concurrent_whisper}
            onChange={(e) => setLocalConfig((c) => ({
              ...c,
              max_concurrent_whisper: Math.min(4, Math.max(1, parseInt(e.target.value) || 1)),
            }))}
            className="w-full px-2.5 py-1.5 rounded text-xs transition-all duration-150 focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
            }}
          />
          <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            Number of simultaneous transcription jobs (1-4). Higher values use more CPU/GPU.
          </p>
        </div>

        {/* Whisper fallback min score */}
        <div className="space-y-1">
          <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
            Fallback Min Score
          </label>
          <input
            type="number"
            min={0}
            max={100}
            value={localConfig.whisper_fallback_min_score}
            onChange={(e) => setLocalConfig((c) => ({
              ...c,
              whisper_fallback_min_score: Math.min(100, Math.max(0, parseInt(e.target.value) || 0)),
            }))}
            className="w-full px-2.5 py-1.5 rounded text-xs transition-all duration-150 focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
            }}
          />
          <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            When all provider results score below this threshold, use Whisper instead. 0 = only when no results at all.
          </p>
        </div>

        {/* Save button */}
        <button
          onClick={handleSaveConfig}
          disabled={saveConfigMut.isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {saveConfigMut.isPending ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Save size={12} />
          )}
          Save Config
        </button>

        {/* Stats summary */}
        {stats && stats.total > 0 && (
          <div className="pt-3 space-y-1" style={{ borderTop: '1px solid var(--border)' }}>
            <div className="flex items-center gap-2">
              <Activity size={12} style={{ color: 'var(--text-muted)' }} />
              <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                Whisper Statistics
              </span>
            </div>
            <div className="flex items-center gap-3 flex-wrap text-xs" style={{ color: 'var(--text-muted)' }}>
              <span>{stats.total} total jobs</span>
              {stats.avg_processing_time > 0 && (
                <span>Avg: {Math.round(stats.avg_processing_time / 1000)}s processing</span>
              )}
              {Object.entries(stats.by_status).map(([status, count]) => (
                <span key={status}>{count} {status}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Backend cards */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
            {backends.length} whisper backend{backends.length !== 1 ? 's' : ''} available &mdash; expand to configure and test
          </span>
        </div>

        {backends.map((backend) => (
          <WhisperBackendCard
            key={backend.name}
            backend={backend}
            onTest={() => handleTest(backend.name)}
            testResult={testResults[backend.name]}
          />
        ))}

        {backends.length === 0 && (
          <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
            No Whisper backends registered. Install faster-whisper or configure Subgen to enable speech-to-text.
          </div>
        )}
      </div>
    </div>
  )
}
