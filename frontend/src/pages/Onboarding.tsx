import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { updateConfig, completeOnboarding, getHealth, getMediaServerTypes, saveMediaServerInstances, testMediaServer } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import { Loader2, CheckCircle, ArrowRight, ArrowLeft, Server, Globe, Cpu, Search, Play, Monitor, Plus, TestTube, Trash2, Eye, EyeOff } from 'lucide-react'
import type { MediaServerType, MediaServerInstance, MediaServerTestResult } from '@/lib/types'

const STEPS = [
  { title: 'Sonarr / Radarr', icon: Server, description: 'Connect your *arr instances to detect missing subtitles.' },
  { title: 'Path Mapping', icon: Globe, description: 'Map remote paths to local paths (if *arr runs on a different host).' },
  { title: 'Providers', icon: Search, description: 'Configure subtitle provider API keys for searching.' },
  { title: 'Ollama', icon: Cpu, description: 'Set up the LLM translation backend.' },
  { title: 'Media Servers (Optional)', icon: Monitor, description: 'Configure media servers for automatic library refresh after subtitle downloads.' },
  { title: 'First Scan', icon: Play, description: 'Run your first wanted scan to find missing subtitles.' },
]

const inputStyle = {
  backgroundColor: 'var(--bg-primary)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-mono)',
  fontSize: '13px',
}

export default function Onboarding() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [scanStarted, setScanStarted] = useState(false)

  const [values, setValues] = useState({
    sonarr_url: '',
    sonarr_api_key: '',
    radarr_url: '',
    radarr_api_key: '',
    path_mapping: '',
    opensubtitles_api_key: '',
    jimaku_api_key: '',
    subdl_api_key: '',
    ollama_url: 'http://localhost:11434',
    ollama_model: 'qwen2.5:14b-instruct',
    target_language: 'de',
    target_language_name: 'German',
    source_language: 'en',
    source_language_name: 'English',
  })

  // Media server state
  const [msTypes, setMsTypes] = useState<MediaServerType[]>([])
  const [msInstances, setMsInstances] = useState<MediaServerInstance[]>([])
  const [msTestResults, setMsTestResults] = useState<Record<number, MediaServerTestResult | 'testing'>>({})
  const [msShowPasswords, setMsShowPasswords] = useState<Record<string, boolean>>({})

  // Load media server types when reaching that step
  useEffect(() => {
    if (step === 4 && msTypes.length === 0) {
      getMediaServerTypes()
        .then(setMsTypes)
        .catch(() => { /* ignore -- types will just be empty */ })
    }
  }, [step, msTypes.length])

  const set = (key: string, val: string) =>
    setValues((v) => ({ ...v, [key]: val }))

  const saveAndNext = async () => {
    setSaving(true)
    try {
      // Only send non-empty values
      const toSave: Record<string, string> = {}
      for (const [k, v] of Object.entries(values)) {
        if (v) toSave[k] = v
      }
      await updateConfig(toSave)

      // If on media server step, also save instances
      if (step === 4 && msInstances.length > 0) {
        await saveMediaServerInstances(msInstances)
      }

      setStep((s) => s + 1)
    } catch {
      toast('Failed to save settings', 'error')
    } finally {
      setSaving(false)
    }
  }

  const testOllama = async () => {
    setTesting(true)
    try {
      const health = await getHealth()
      if (health.services?.ollama && !health.services.ollama.includes('error')) {
        toast('Ollama connection successful!')
      } else {
        toast('Ollama not reachable', 'error')
      }
    } catch {
      toast('Connection test failed', 'error')
    } finally {
      setTesting(false)
    }
  }

  const startScan = async () => {
    setScanStarted(true)
    try {
      const { refreshWanted } = await import('@/api/client')
      await refreshWanted()
      toast('Wanted scan started!')
    } catch {
      toast('Scan failed', 'error')
    }
  }

  const finish = async () => {
    try {
      await completeOnboarding()
      navigate('/')
    } catch {
      navigate('/')
    }
  }

  // Media server helpers
  const addMediaServer = (serverType: MediaServerType) => {
    const newInst: MediaServerInstance = {
      type: serverType.name,
      name: serverType.display_name,
      enabled: true,
    }
    for (const field of serverType.config_fields) {
      newInst[field.key] = field.default ?? ''
    }
    setMsInstances((prev) => [...prev, newInst])
  }

  const updateMsField = (idx: number, key: string, value: unknown) => {
    setMsInstances((prev) => {
      const updated = [...prev]
      updated[idx] = { ...updated[idx], [key]: value }
      return updated
    })
  }

  const removeMsInstance = (idx: number) => {
    setMsInstances((prev) => prev.filter((_, i) => i !== idx))
  }

  const testMsInstance = async (idx: number) => {
    const inst = msInstances[idx]
    setMsTestResults((prev) => ({ ...prev, [idx]: 'testing' }))
    try {
      const result = await testMediaServer(inst as Record<string, unknown>)
      setMsTestResults((prev) => ({ ...prev, [idx]: result }))
      if (result.healthy) {
        toast(`${inst.name}: connection successful`)
      } else {
        toast(`${inst.name}: ${result.message}`, 'error')
      }
    } catch {
      setMsTestResults((prev) => ({ ...prev, [idx]: { healthy: false, message: 'Test request failed' } }))
      toast(`${inst.name}: test failed`, 'error')
    }
  }

  const Field = ({ label, keyName, type = 'text', placeholder = '' }: {
    label: string; keyName: string; type?: string; placeholder?: string
  }) => (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
        {label}
      </label>
      <input
        type={type}
        value={values[keyName as keyof typeof values] ?? ''}
        onChange={(e) => set(keyName, e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
        style={inputStyle}
      />
    </div>
  )

  return (
    <div className="min-h-screen flex items-center justify-center p-6" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <div className="w-full max-w-xl space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
            Welcome to Sublarr
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Let's set up your subtitle manager in a few quick steps.
          </p>
        </div>

        {/* Progress */}
        <div className="flex items-center gap-1">
          {STEPS.map((s, i) => (
            <div key={i} className="flex-1 flex items-center gap-1">
              <div
                className="h-1.5 flex-1 rounded-full transition-all duration-300"
                style={{
                  backgroundColor: i <= step ? 'var(--accent)' : 'var(--border)',
                }}
              />
            </div>
          ))}
        </div>

        {/* Step Content */}
        <div
          className="rounded-lg p-6 space-y-5"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center gap-3">
            {(() => {
              const Icon = STEPS[step].icon
              return <Icon size={20} style={{ color: 'var(--accent)' }} />
            })()}
            <div>
              <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                {STEPS[step].title}
              </h2>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Step {step + 1} of {STEPS.length} &mdash; {STEPS[step].description}
              </p>
            </div>
          </div>

          {step === 0 && (
            <div className="space-y-4">
              <Field label="Sonarr URL" keyName="sonarr_url" placeholder="http://localhost:8989" />
              <Field label="Sonarr API Key" keyName="sonarr_api_key" type="password" />
              <Field label="Radarr URL (optional)" keyName="radarr_url" placeholder="http://localhost:7878" />
              <Field label="Radarr API Key (optional)" keyName="radarr_api_key" type="password" />
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <Field
                label="Path Mapping"
                keyName="path_mapping"
                placeholder="/data/media=/mnt/media;/anime=/share/anime"
              />
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Format: remote_prefix=local_prefix (semicolon-separated for multiple).
                Leave empty if Sublarr runs on the same host as Sonarr/Radarr.
              </p>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                AnimeTosho works without an API key. Add others for broader coverage.
              </p>
              <Field label="OpenSubtitles API Key" keyName="opensubtitles_api_key" type="password" />
              <Field label="Jimaku API Key" keyName="jimaku_api_key" type="password" />
              <Field label="SubDL API Key" keyName="subdl_api_key" type="password" />
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <Field label="Ollama URL" keyName="ollama_url" placeholder="http://localhost:11434" />
              <Field label="Ollama Model" keyName="ollama_model" placeholder="qwen2.5:14b-instruct" />
              <div className="grid grid-cols-2 gap-3">
                <Field label="Source Language" keyName="source_language" placeholder="en" />
                <Field label="Source Language Name" keyName="source_language_name" placeholder="English" />
                <Field label="Target Language" keyName="target_language" placeholder="de" />
                <Field label="Target Language Name" keyName="target_language_name" placeholder="German" />
              </div>
              <button
                onClick={testOllama}
                disabled={testing}
                className="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
                style={{
                  border: '1px solid var(--border)',
                  color: 'var(--text-secondary)',
                  backgroundColor: 'var(--bg-primary)',
                }}
              >
                {testing ? <Loader2 size={14} className="animate-spin" /> : <Cpu size={14} />}
                Test Ollama Connection
              </button>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-4">
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                Add media servers for automatic library refresh after subtitle downloads. You can skip this and configure later in Settings.
              </p>

              {/* Type selection buttons */}
              <div className="flex flex-wrap gap-2">
                {msTypes.map((t) => (
                  <button
                    key={t.name}
                    onClick={() => addMediaServer(t)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
                    style={{
                      border: '1px solid var(--accent-dim)',
                      color: 'var(--accent)',
                      backgroundColor: 'var(--accent-bg)',
                    }}
                  >
                    <Plus size={14} />
                    {t.display_name}
                  </button>
                ))}
              </div>

              {/* Configured instances */}
              {msInstances.map((inst, idx) => {
                const typeInfo = msTypes.find((t) => t.name === inst.type)
                const testResult = msTestResults[idx]

                return (
                  <div
                    key={idx}
                    className="rounded-lg p-4 space-y-3"
                    style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                          {inst.name}
                        </span>
                        <span
                          className="px-2 py-0.5 rounded-full text-[10px] font-medium"
                          style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
                        >
                          {typeInfo?.display_name ?? inst.type}
                        </span>
                      </div>
                      <button
                        onClick={() => removeMsInstance(idx)}
                        className="p-1 rounded transition-colors"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>

                    {/* Name */}
                    <input
                      type="text"
                      value={String(inst.name ?? '')}
                      onChange={(e) => updateMsField(idx, 'name', e.target.value)}
                      placeholder="Server name"
                      className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
                      style={inputStyle}
                    />

                    {/* Dynamic config fields */}
                    {typeInfo?.config_fields.map((field) => (
                      <div key={field.key} className="space-y-1">
                        <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                          {field.label} {field.required && <span style={{ color: 'var(--error)' }}>*</span>}
                        </label>
                        <div className="flex items-center gap-1.5">
                          <input
                            type={field.type === 'password' && !msShowPasswords[`${idx}-${field.key}`] ? 'password' : 'text'}
                            value={String(inst[field.key] ?? '')}
                            onChange={(e) => updateMsField(idx, field.key, e.target.value)}
                            placeholder={field.default || (field.required ? 'Required' : 'Optional')}
                            className="flex-1 px-2.5 py-1.5 rounded text-sm focus:outline-none"
                            style={inputStyle}
                          />
                          {field.type === 'password' && (
                            <button
                              onClick={() => setMsShowPasswords((p) => ({ ...p, [`${idx}-${field.key}`]: !p[`${idx}-${field.key}`] }))}
                              className="p-1.5 rounded"
                              style={{ border: '1px solid var(--border)', color: 'var(--text-muted)', backgroundColor: 'var(--bg-primary)' }}
                            >
                              {msShowPasswords[`${idx}-${field.key}`] ? <EyeOff size={12} /> : <Eye size={12} />}
                            </button>
                          )}
                        </div>
                      </div>
                    ))}

                    {/* Test button and result */}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => testMsInstance(idx)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150"
                        style={{
                          border: '1px solid var(--border)',
                          color: 'var(--text-secondary)',
                          backgroundColor: 'var(--bg-surface)',
                        }}
                      >
                        {testResult === 'testing' ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <TestTube size={12} />
                        )}
                        Test
                      </button>
                      {testResult && testResult !== 'testing' && (
                        <span className="text-xs" style={{ color: testResult.healthy ? 'var(--success)' : 'var(--error)' }}>
                          {testResult.healthy ? 'OK' : 'Error'}: {testResult.message}
                        </span>
                      )}
                    </div>
                  </div>
                )
              })}

              {msInstances.length === 0 && msTypes.length === 0 && (
                <div className="text-center py-4">
                  <Loader2 size={16} className="animate-spin mx-auto" style={{ color: 'var(--accent)' }} />
                </div>
              )}
            </div>
          )}

          {step === 5 && (
            <div className="space-y-4 text-center">
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                Run a scan to find episodes and movies missing subtitles.
              </p>
              {!scanStarted ? (
                <button
                  onClick={startScan}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-medium text-white"
                  style={{ backgroundColor: 'var(--accent)' }}
                >
                  <Play size={16} />
                  Start First Scan
                </button>
              ) : (
                <div className="flex items-center justify-center gap-2" style={{ color: 'var(--success)' }}>
                  <CheckCircle size={18} />
                  <span className="text-sm font-medium">Scan started! Check the Wanted page for results.</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between">
          <button
            onClick={() => step > 0 ? setStep((s) => s - 1) : navigate('/')}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm"
            style={{ color: 'var(--text-muted)' }}
          >
            <ArrowLeft size={14} />
            {step > 0 ? 'Back' : 'Skip Setup'}
          </button>

          {step < STEPS.length - 1 ? (
            <button
              onClick={saveAndNext}
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium text-white"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : null}
              {step === 4 ? (msInstances.length > 0 ? 'Save & Next' : 'Skip') : 'Next'}
              <ArrowRight size={14} />
            </button>
          ) : (
            <button
              onClick={finish}
              className="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium text-white"
              style={{ backgroundColor: 'var(--success)' }}
            >
              <CheckCircle size={14} />
              Finish Setup
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
