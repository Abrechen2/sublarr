import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { updateConfig, completeOnboarding, getHealth } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import { Loader2, CheckCircle, ArrowRight, ArrowLeft, Server, Globe, Cpu, Search, Play } from 'lucide-react'

const STEPS = [
  { title: 'Sonarr / Radarr', icon: Server, description: 'Connect your *arr instances to detect missing subtitles.' },
  { title: 'Path Mapping', icon: Globe, description: 'Map remote paths to local paths (if *arr runs on a different host).' },
  { title: 'Providers', icon: Search, description: 'Configure subtitle provider API keys for searching.' },
  { title: 'Ollama', icon: Cpu, description: 'Set up the LLM translation backend.' },
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
      if (health.ollama?.healthy) {
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
              Next
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
