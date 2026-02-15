import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { updateConfig, completeOnboarding, getHealth, getMediaServerTypes, saveMediaServerInstances, testMediaServer, saveWatchedFolder, triggerStandaloneScan } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import { Loader2, CheckCircle, ArrowRight, ArrowLeft, Server, Globe, Cpu, Search, Play, Monitor, Plus, TestTube, Trash2, Eye, EyeOff, FolderOpen } from 'lucide-react'
import type { MediaServerType, MediaServerInstance, MediaServerTestResult } from '@/lib/types'

const ALL_STEPS = [
  { id: 'mode', title: 'Setup Mode', icon: Server, description: 'Choose how you want to use Sublarr.' },
  { id: 'arr', title: 'Sonarr / Radarr', icon: Server, description: 'Connect your *arr instances to detect missing subtitles.' },
  { id: 'standalone', title: 'Standalone Folders', icon: FolderOpen, description: 'Point Sublarr at your media folders directly.' },
  { id: 'pathmapping', title: 'Path Mapping', icon: Globe, description: 'Map remote paths to local paths (if *arr runs on a different host).' },
  { id: 'providers', title: 'Providers', icon: Search, description: 'Configure subtitle provider API keys for searching.' },
  { id: 'ollama', title: 'Ollama', icon: Cpu, description: 'Set up the LLM translation backend.' },
  { id: 'mediaservers', title: 'Media Servers (Optional)', icon: Monitor, description: 'Configure media servers for automatic library refresh after subtitle downloads.' },
  { id: 'scan', title: 'First Scan', icon: Play, description: 'Run your first wanted scan to find missing subtitles.' },
]

function getVisibleSteps(setupMode: 'arr' | 'standalone' | null) {
  if (!setupMode) return [ALL_STEPS[0]] // only setup mode step
  if (setupMode === 'arr') {
    return ALL_STEPS.filter(s => ['mode', 'arr', 'pathmapping', 'providers', 'ollama', 'mediaservers', 'scan'].includes(s.id))
  }
  // standalone: skip arr and pathmapping
  return ALL_STEPS.filter(s => ['mode', 'standalone', 'providers', 'ollama', 'mediaservers', 'scan'].includes(s.id))
}

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
  const [setupMode, setSetupMode] = useState<'arr' | 'standalone' | null>(null)

  const visibleSteps = getVisibleSteps(setupMode)
  const currentStepDef = visibleSteps[step] || visibleSteps[0]

  // Standalone folder state
  const [standaloneFolders, setStandaloneFolders] = useState<{ path: string; label: string }[]>([])
  const [newFolderPath, setNewFolderPath] = useState('')

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
    tmdb_api_key: '',
    tvdb_api_key: '',
  })

  // Media server state
  const [msTypes, setMsTypes] = useState<MediaServerType[]>([])
  const [msInstances, setMsInstances] = useState<MediaServerInstance[]>([])
  const [msTestResults, setMsTestResults] = useState<Record<number, MediaServerTestResult | 'testing'>>({})
  const [msShowPasswords, setMsShowPasswords] = useState<Record<string, boolean>>({})

  // Load media server types when reaching that step
  useEffect(() => {
    if (currentStepDef.id === 'mediaservers' && msTypes.length === 0) {
      getMediaServerTypes()
        .then(setMsTypes)
        .catch(() => { /* ignore -- types will just be empty */ })
    }
  }, [currentStepDef.id, msTypes.length])

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

      // If on standalone step, enable standalone mode and save folders
      if (currentStepDef.id === 'standalone') {
        toSave.standalone_enabled = 'true'
        await updateConfig(toSave)
        // Save each folder
        for (const folder of standaloneFolders) {
          if (folder.path.trim()) {
            await saveWatchedFolder({ path: folder.path.trim(), label: folder.label.trim(), media_type: 'auto', enabled: true })
          }
        }
      } else {
        await updateConfig(toSave)
      }

      // If on media server step, also save instances
      if (currentStepDef.id === 'mediaservers' && msInstances.length > 0) {
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
      if (setupMode === 'standalone') {
        await triggerStandaloneScan()
        toast('Standalone scan started!')
      } else {
        const { refreshWanted } = await import('@/api/client')
        await refreshWanted()
        toast('Wanted scan started!')
      }
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
          {visibleSteps.map((s, i) => (
            <div key={s.id} className="flex-1 flex items-center gap-1">
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
              const Icon = currentStepDef.icon
              return <Icon size={20} style={{ color: 'var(--accent)' }} />
            })()}
            <div>
              <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                {currentStepDef.title}
              </h2>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Step {step + 1} of {visibleSteps.length} &mdash; {currentStepDef.description}
              </p>
            </div>
          </div>

          {currentStepDef.id === 'mode' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {/* Sonarr / Radarr Mode card */}
                <button
                  onClick={() => { setSetupMode('arr'); setStep(1) }}
                  className="rounded-lg p-4 text-left space-y-2 transition-all duration-200"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    border: setupMode === 'arr' ? '2px solid var(--accent)' : '1px solid var(--border)',
                  }}
                  onMouseEnter={(e) => { if (setupMode !== 'arr') e.currentTarget.style.borderColor = 'var(--accent-dim)' }}
                  onMouseLeave={(e) => { if (setupMode !== 'arr') e.currentTarget.style.borderColor = 'var(--border)' }}
                >
                  <div className="flex items-center justify-between">
                    <Server size={20} style={{ color: 'var(--accent)' }} />
                    {setupMode === 'arr' && <CheckCircle size={16} style={{ color: 'var(--accent)' }} />}
                  </div>
                  <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                    Sonarr / Radarr Mode
                  </div>
                  <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    Use with Sonarr and/or Radarr for automatic media detection
                  </div>
                </button>

                {/* Standalone Mode card */}
                <button
                  onClick={() => { setSetupMode('standalone'); setStep(1) }}
                  className="rounded-lg p-4 text-left space-y-2 transition-all duration-200"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    border: setupMode === 'standalone' ? '2px solid var(--accent)' : '1px solid var(--border)',
                  }}
                  onMouseEnter={(e) => { if (setupMode !== 'standalone') e.currentTarget.style.borderColor = 'var(--accent-dim)' }}
                  onMouseLeave={(e) => { if (setupMode !== 'standalone') e.currentTarget.style.borderColor = 'var(--border)' }}
                >
                  <div className="flex items-center justify-between">
                    <FolderOpen size={20} style={{ color: 'var(--accent)' }} />
                    {setupMode === 'standalone' && <CheckCircle size={16} style={{ color: 'var(--accent)' }} />}
                  </div>
                  <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                    Standalone Mode
                  </div>
                  <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    Point at media folders directly, no Sonarr/Radarr needed
                  </div>
                </button>
              </div>
            </div>
          )}

          {currentStepDef.id === 'arr' && (
            <div className="space-y-4">
              <Field label="Sonarr URL" keyName="sonarr_url" placeholder="http://localhost:8989" />
              <Field label="Sonarr API Key" keyName="sonarr_api_key" type="password" />
              <Field label="Radarr URL (optional)" keyName="radarr_url" placeholder="http://localhost:7878" />
              <Field label="Radarr API Key (optional)" keyName="radarr_api_key" type="password" />
            </div>
          )}

          {currentStepDef.id === 'standalone' && (
            <div className="space-y-4">
              <Field label="TMDB API Key (required for metadata)" keyName="tmdb_api_key" type="password" />
              <Field label="TVDB API Key (optional)" keyName="tvdb_api_key" type="password" />
              <div className="space-y-2">
                <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  Media Folders
                </label>
                {standaloneFolders.map((folder, idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <input
                      type="text"
                      value={folder.path}
                      onChange={(e) => {
                        const updated = [...standaloneFolders]
                        updated[idx] = { ...updated[idx], path: e.target.value }
                        setStandaloneFolders(updated)
                      }}
                      placeholder="/path/to/media"
                      className="flex-1 px-3 py-2 rounded-md text-sm focus:outline-none"
                      style={{ ...inputStyle, fontFamily: 'var(--font-mono)' }}
                    />
                    <button
                      onClick={() => setStandaloneFolders((prev) => prev.filter((_, i) => i !== idx))}
                      className="p-1.5 rounded transition-colors"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={newFolderPath}
                    onChange={(e) => setNewFolderPath(e.target.value)}
                    placeholder="/path/to/media"
                    className="flex-1 px-3 py-2 rounded-md text-sm focus:outline-none"
                    style={{ ...inputStyle, fontFamily: 'var(--font-mono)' }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && newFolderPath.trim()) {
                        setStandaloneFolders((prev) => [...prev, { path: newFolderPath.trim(), label: '' }])
                        setNewFolderPath('')
                      }
                    }}
                  />
                  <button
                    onClick={() => {
                      if (newFolderPath.trim()) {
                        setStandaloneFolders((prev) => [...prev, { path: newFolderPath.trim(), label: '' }])
                        setNewFolderPath('')
                      }
                    }}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
                    style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
                  >
                    <Plus size={14} />
                    Add
                  </button>
                </div>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  Add folders containing your media files. Sublarr will scan them for series and movies.
                </p>
              </div>
            </div>
          )}

          {currentStepDef.id === 'pathmapping' && (
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

          {currentStepDef.id === 'providers' && (
            <div className="space-y-4">
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                AnimeTosho works without an API key. Add others for broader coverage.
              </p>
              <Field label="OpenSubtitles API Key" keyName="opensubtitles_api_key" type="password" />
              <Field label="Jimaku API Key" keyName="jimaku_api_key" type="password" />
              <Field label="SubDL API Key" keyName="subdl_api_key" type="password" />
            </div>
          )}

          {currentStepDef.id === 'ollama' && (
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

          {currentStepDef.id === 'mediaservers' && (
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

          {currentStepDef.id === 'scan' && (
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

          {step < visibleSteps.length - 1 ? (
            <button
              onClick={saveAndNext}
              disabled={saving || currentStepDef.id === 'mode'}
              className="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium text-white"
              style={{ backgroundColor: currentStepDef.id === 'mode' ? 'var(--text-muted)' : 'var(--accent)' }}
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : null}
              {currentStepDef.id === 'mediaservers' ? (msInstances.length > 0 ? 'Save & Next' : 'Skip') : 'Next'}
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
