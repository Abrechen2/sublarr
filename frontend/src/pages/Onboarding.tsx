import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { updateConfig, completeOnboarding, getHealth, getMediaServerTypes, saveMediaServerInstances, testMediaServer, saveWatchedFolder, triggerStandaloneScan } from '@/api/client'
import { testSonarrInstance, testRadarrInstance, testApiKey } from '@/api/settings'
import { toast } from '@/components/shared/Toast'
import { Loader2, CheckCircle, ArrowRight, ArrowLeft, Server, Globe, Cpu, Search, Play, Monitor, Plus, TestTube, Trash2, Eye, EyeOff, FolderOpen, Languages, Zap, AlertCircle } from 'lucide-react'
import type { MediaServerType, MediaServerInstance, MediaServerTestResult } from '@/lib/types'

export const ALL_STEPS = [
  { id: 'mode', titleKey: 'steps.mode', icon: Server, descKey: 'mode_step.description' },
  { id: 'arr', titleKey: 'steps.arr', icon: Server, descKey: 'arr_step.description' },
  { id: 'standalone', titleKey: 'steps.standalone', icon: FolderOpen, descKey: 'standalone_step.description' },
  { id: 'pathmapping', titleKey: 'steps.pathmapping', icon: Globe, descKey: 'pathmapping_step.description' },
  { id: 'language', titleKey: 'steps.language', icon: Languages, descKey: 'language_step.description' },
  { id: 'providers', titleKey: 'steps.providers', icon: Search, descKey: 'providers_step.description' },
  { id: 'automation', titleKey: 'steps.automation', icon: Zap, descKey: 'automation_step.description' },
  { id: 'ollama', titleKey: 'steps.ollama', icon: Cpu, descKey: 'ollama_step.description' },
  { id: 'mediaservers', titleKey: 'steps.mediaservers', icon: Monitor, descKey: 'mediaservers_step.description' },
  { id: 'scan', titleKey: 'steps.scan', icon: Play, descKey: 'scan_step.description' },
]

export function getVisibleSteps(setupMode: 'arr' | 'standalone' | null) {
  if (!setupMode) return [ALL_STEPS[0]] // only setup mode step
  if (setupMode === 'arr') {
    return ALL_STEPS.filter(s =>
      ['mode', 'arr', 'pathmapping', 'language', 'providers', 'automation', 'ollama', 'mediaservers', 'scan'].includes(s.id)
    )
  }
  // standalone: skip arr and pathmapping
  return ALL_STEPS.filter(s =>
    ['mode', 'standalone', 'language', 'providers', 'automation', 'ollama', 'mediaservers', 'scan'].includes(s.id)
  )
}

const inputStyle = {
  backgroundColor: 'var(--bg-primary)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-mono)',
  fontSize: '13px',
}

// Single source of truth for the onboarding language dropdowns (N4).
// Order matters — the first entry is the default offered to new users.
const TARGET_LANG_CODES = ['de','en','fr','es','it','pt','nl','pl','zh','ja','ko','hr','sr','cs','hu','ro','tr','ru','ar','he','el'] as const
const SOURCE_LANG_CODES = ['en','ja','ko','zh','de','fr','es'] as const

// Module-level Field input (B1). Defining inputs inside the parent component
// remounts the underlying <input> on every render, which drops keyboard focus
// after every keystroke. Caller resolves value + onChange explicitly so this
// component carries no closure over parent state.
type FieldProps = {
  label: string
  type?: string
  placeholder?: string
  value: string
  onChange: (next: string) => void
  autoComplete?: string
}

function Field({ label, type = 'text', placeholder = '', value, onChange, autoComplete }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete ?? (type === 'password' ? 'new-password' : 'off')}
        spellCheck={false}
        className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
        style={inputStyle}
      />
    </div>
  )
}

let _uid = 0
const nextUid = () => `ms-${++_uid}-${Date.now().toString(36)}`

export default function Onboarding() {
  const { t } = useTranslation('onboarding')
  const { t: tc } = useTranslation('common')
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [saving, setSaving] = useState(false)
  // Tracks which connection test is in-flight ('sonarr' | 'radarr' | 'ollama' | null)
  // so concurrent click on a different button doesn't show the wrong spinner.
  const [testing, setTesting] = useState<string | null>(null)
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
    automation_enabled: 'true',
    search_interval_hours: '6',
    upgrade_enabled: 'true',
  })

  // Media server state.
  // Stable per-instance ids decouple show-password / test-result state from the
  // array index, so removing instance #1 doesn't shift visibility flags from #2
  // onto the wrong row (N1). Two parallel arrays kept in sync via add/remove.
  const [msTypes, setMsTypes] = useState<MediaServerType[]>([])
  const [msInstances, setMsInstances] = useState<MediaServerInstance[]>([])
  const msInstanceIds = useRef<string[]>([])
  const [msTestResults, setMsTestResults] = useState<Record<string, MediaServerTestResult | 'testing'>>({})
  const [msShowPasswords, setMsShowPasswords] = useState<Record<string, boolean>>({})
  const [msTypesError, setMsTypesError] = useState(false)

  // Load media server types when reaching that step. On failure we surface a
  // retry button (N3); the previous catch block ignored the error so users sat
  // in front of an indefinite loading spinner.
  const loadMsTypes = () => {
    setMsTypesError(false)
    getMediaServerTypes()
      .then((ts) => setMsTypes(ts))
      .catch(() => setMsTypesError(true))
  }

  useEffect(() => {
    if (currentStepDef.id === 'mediaservers' && msTypes.length === 0 && !msTypesError) {
      loadMsTypes()
    }
  }, [currentStepDef.id, msTypes.length, msTypesError])

  const set = (key: string, val: string) =>
    setValues((v) => ({ ...v, [key]: val }))

  // Keys that only apply to one setup mode. saveAndNext filters by setupMode
  // so a user who fills Sonarr credentials, goes back, and switches to
  // standalone doesn't POST the stale Sonarr keys (B16).
  const ARR_ONLY_KEYS = ['sonarr_url','sonarr_api_key','radarr_url','radarr_api_key','path_mapping'] as const
  const STANDALONE_ONLY_KEYS = ['tmdb_api_key','tvdb_api_key'] as const

  const saveAndNext = async () => {
    setSaving(true)
    try {
      // Build the payload, then drop keys that belong to the *other* setup mode.
      const toSave: Record<string, string> = {}
      for (const [k, v] of Object.entries(values)) {
        if (v) toSave[k] = v
      }
      if (setupMode === 'arr') {
        for (const k of STANDALONE_ONLY_KEYS) delete toSave[k]
      } else if (setupMode === 'standalone') {
        for (const k of ARR_ONLY_KEYS) delete toSave[k]
      }

      if (currentStepDef.id === 'standalone') {
        toSave.standalone_enabled = 'true'
        await updateConfig(toSave)
        // Save folders concurrently so one bad path doesn't block the rest (B11).
        const folderPayloads = standaloneFolders
          .filter((f) => f.path.trim())
          .map((folder) => saveWatchedFolder({
            path: folder.path.trim(),
            label: folder.label.trim(),
            media_type: 'auto',
            enabled: true,
          }))
        const folderResults = await Promise.allSettled(folderPayloads)
        const folderFailures = folderResults.filter((r) => r.status === 'rejected').length
        if (folderFailures > 0) {
          toast(t('errors.folder_save', { count: folderFailures }), 'error')
        }
      } else {
        await updateConfig(toSave)
      }

      if (currentStepDef.id === 'mediaservers' && msInstances.length > 0) {
        await saveMediaServerInstances(msInstances)
      }

      setStep((s) => s + 1)
    } catch {
      toast(t('errors.save_failed'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const testOllama = async () => {
    setTesting('ollama')
    try {
      const health = await getHealth()
      if (health.services?.ollama && !health.services.ollama.includes('error')) {
        toast(t('ollama_step.connection_successful'))
      } else {
        toast(t('ollama_step.connection_failed'), 'error')
      }
    } catch {
      toast(t('ollama_step.test_failed'), 'error')
    } finally {
      setTesting(null)
    }
  }

  // Inline connection test for arr-step credentials. Sonarr/Radarr have a
  // dedicated `/instances/test` endpoint that accepts {url, api_key} so we can
  // validate without persisting the value first.
  const runConnectionTest = async (which: 'sonarr' | 'radarr') => {
    const url = which === 'sonarr' ? values.sonarr_url : values.radarr_url
    const api_key = which === 'sonarr' ? values.sonarr_api_key : values.radarr_api_key
    if (!url || !api_key) return
    setTesting(which)
    try {
      const fn = which === 'sonarr' ? testSonarrInstance : testRadarrInstance
      const result = await fn({ url, api_key })
      toast(`${which}: ${result.message || (result.healthy ? 'OK' : 'Error')}`, result.healthy ? 'success' : 'error')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      toast(`${which}: ${msg}`, 'error')
    } finally {
      setTesting(null)
    }
  }

  // TMDB/TVDB tests require the key to be persisted first (the backend test_fn
  // looks up the client from saved config). Persist then test.
  const runApiKeyTest = async (service: 'tmdb' | 'tvdb') => {
    const key = service === 'tmdb' ? values.tmdb_api_key : values.tvdb_api_key
    if (!key) return
    setTesting(service)
    try {
      await updateConfig({ [`${service}_api_key`]: key })
      const result = await testApiKey(service)
      toast(`${service}: ${result.message}`, result.success ? 'success' : 'error')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      toast(`${service}: ${msg}`, 'error')
    } finally {
      setTesting(null)
    }
  }

  const startScan = async () => {
    try {
      if (setupMode === 'standalone') {
        await triggerStandaloneScan()
        setScanStarted(true)
        toast(t('scan_step.standalone_scan_started'))
      } else {
        const { refreshWanted } = await import('@/api/client')
        await refreshWanted()
        setScanStarted(true)
        toast(t('scan_step.wanted_scan_started'))
      }
    } catch {
      toast(t('scan_step.scan_failed'), 'error')
    }
  }

  const finish = async () => {
    try {
      await completeOnboarding()
      navigate('/')
    } catch {
      // Don't swallow — user needs to know finalisation failed so they can retry (B6).
      toast(t('errors.complete_failed'), 'error')
    }
  }

  // "Skip Setup" should still mark onboarding complete on the backend; otherwise
  // the wizard is shown again on the next visit and any partially-saved config
  // is left in limbo (N2).
  const skipSetup = async () => {
    try {
      await completeOnboarding()
    } catch {
      // best-effort: navigation still happens so the user is unblocked.
    }
    navigate('/')
  }

  // Switching setup mode mid-flow used to leave stale credentials in `values`
  // that would later be POSTed by saveAndNext (B16). Clear keys that no longer
  // apply when the user picks a different mode card.
  const chooseSetupMode = (mode: 'arr' | 'standalone') => {
    setSetupMode(mode)
    setStep(1)
    setValues((v) => {
      const next = { ...v }
      const clearKeys = mode === 'arr' ? STANDALONE_ONLY_KEYS : ARR_ONLY_KEYS
      for (const k of clearKeys) next[k as keyof typeof next] = ''
      return next
    })
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
    msInstanceIds.current = [...msInstanceIds.current, nextUid()]
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
    const removedId = msInstanceIds.current[idx]
    msInstanceIds.current = msInstanceIds.current.filter((_, i) => i !== idx)
    setMsInstances((prev) => prev.filter((_, i) => i !== idx))
    // Clean up companion state keyed by the removed uid so leftover entries
    // don't bleed onto a future row with the same array index (N1).
    if (removedId) {
      setMsTestResults((prev) => {
        const next = { ...prev }
        delete next[removedId]
        return next
      })
      setMsShowPasswords((prev) => {
        const next: Record<string, boolean> = {}
        for (const [k, v] of Object.entries(prev)) {
          if (!k.startsWith(`${removedId}-`)) next[k] = v
        }
        return next
      })
    }
  }

  const testMsInstance = async (idx: number) => {
    const inst = msInstances[idx]
    const uid = msInstanceIds.current[idx]
    if (!uid) return
    setMsTestResults((prev) => ({ ...prev, [uid]: 'testing' }))
    try {
      const result = await testMediaServer(inst as Record<string, unknown>)
      setMsTestResults((prev) => ({ ...prev, [uid]: result }))
      if (result.healthy) {
        toast(`${inst.name}: ${t('mediaservers_step.connection_successful')}`)
      } else {
        toast(`${inst.name}: ${result.message}`, 'error')
      }
    } catch {
      setMsTestResults((prev) => ({ ...prev, [uid]: { healthy: false, message: t('mediaservers_step.test_failed') } }))
      toast(`${inst.name}: ${t('mediaservers_step.test_failed')}`, 'error')
    }
  }

  // Helper that resolves a `values` key to a controlled-input prop pair, so
  // each <Field /> only needs to know its target key once.
  const fieldFor = (keyName: keyof typeof values) => ({
    value: values[keyName] ?? '',
    onChange: (v: string) => set(keyName, v),
  })

  return (
    <div className="min-h-screen flex items-center justify-center p-6" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <div className="w-full max-w-xl space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
            {t('welcome.title')}
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {t('welcome.subtitle')}
          </p>
        </div>

        {/* Progress (N5 — semantic progressbar for assistive tech) */}
        <div
          className="flex items-center gap-1"
          role="progressbar"
          aria-valuenow={step + 1}
          aria-valuemin={1}
          aria-valuemax={visibleSteps.length}
          aria-label={t('step_info', { step: step + 1, total: visibleSteps.length })}
        >
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
                {t(currentStepDef.titleKey)}
              </h2>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                {t('step_info', { step: step + 1, total: visibleSteps.length })} &mdash; {t(currentStepDef.descKey)}
              </p>
            </div>
          </div>

          {currentStepDef.id === 'mode' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {/* Sonarr / Radarr Mode card */}
                <button
                  onClick={() => chooseSetupMode('arr')}
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
                    {t('mode_step.arr_title')}
                  </div>
                  <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {t('mode_step.arr_description')}
                  </div>
                </button>

                {/* Standalone Mode card */}
                <button
                  onClick={() => chooseSetupMode('standalone')}
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
                    {t('mode_step.standalone_title')}
                  </div>
                  <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {t('mode_step.standalone_description')}
                  </div>
                </button>
              </div>
            </div>
          )}

          {currentStepDef.id === 'arr' && (
            <div className="space-y-4">
              <Field label={t('arr_step.sonarr_url')} placeholder="http://localhost:8989" {...fieldFor('sonarr_url')} />
              <Field label={t('arr_step.sonarr_api_key')} type="password" {...fieldFor('sonarr_api_key')} />
              <button
                type="button"
                onClick={() => runConnectionTest('sonarr')}
                disabled={!values.sonarr_url || !values.sonarr_api_key || testing === 'sonarr'}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150 disabled:opacity-50"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
              >
                {testing === 'sonarr' ? <Loader2 size={12} className="animate-spin" /> : <TestTube size={12} />}
                {t('arr_step.test_sonarr')}
              </button>
              <Field label={t('arr_step.radarr_url')} placeholder="http://localhost:7878" {...fieldFor('radarr_url')} />
              <Field label={t('arr_step.radarr_api_key')} type="password" {...fieldFor('radarr_api_key')} />
              <button
                type="button"
                onClick={() => runConnectionTest('radarr')}
                disabled={!values.radarr_url || !values.radarr_api_key || testing === 'radarr'}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150 disabled:opacity-50"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
              >
                {testing === 'radarr' ? <Loader2 size={12} className="animate-spin" /> : <TestTube size={12} />}
                {t('arr_step.test_radarr')}
              </button>
            </div>
          )}

          {currentStepDef.id === 'standalone' && (
            <div className="space-y-4">
              <Field label={t('standalone_step.tmdb_api_key')} type="password" {...fieldFor('tmdb_api_key')} />
              <button
                type="button"
                onClick={() => runApiKeyTest('tmdb')}
                disabled={!values.tmdb_api_key || testing === 'tmdb'}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150 disabled:opacity-50"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
              >
                {testing === 'tmdb' ? <Loader2 size={12} className="animate-spin" /> : <TestTube size={12} />}
                {t('standalone_step.test_tmdb')}
              </button>
              <Field label={t('standalone_step.tvdb_api_key')} type="password" {...fieldFor('tvdb_api_key')} />
              <button
                type="button"
                onClick={() => runApiKeyTest('tvdb')}
                disabled={!values.tvdb_api_key || testing === 'tvdb'}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150 disabled:opacity-50"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
              >
                {testing === 'tvdb' ? <Loader2 size={12} className="animate-spin" /> : <TestTube size={12} />}
                {t('standalone_step.test_tvdb')}
              </button>
              <div className="space-y-2">
                <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {t('standalone_step.media_folders')}
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
                    {t('common:actions.add')}
                  </button>
                </div>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {t('standalone_step.media_folders_help')}
                </p>
              </div>
            </div>
          )}

          {currentStepDef.id === 'pathmapping' && (
            <div className="space-y-4">
              <Field
                label={t('pathmapping_step.label')}
                placeholder={t('pathmapping_step.placeholder')}
                {...fieldFor('path_mapping')}
              />
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                {t('pathmapping_step.help')}
              </p>
            </div>
          )}

          {currentStepDef.id === 'language' && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {t('language_step.target_language')}
                </label>
                <select
                  value={values.target_language}
                  // Sync the display-name alongside the code (B3). The two were
                  // independent state keys; if only the code changed the cached
                  // name would drift (target_language='fr', name='German').
                  onChange={(e) => {
                    const code = e.target.value
                    setValues((v) => ({
                      ...v,
                      target_language: code,
                      target_language_name: tc(`language_names.${code}`).replace(/\s*\([a-z]+\)\s*$/, ''),
                    }))
                  }}
                  className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
                  style={inputStyle}
                >
                  {TARGET_LANG_CODES.map((code) => (
                    <option key={code} value={code}>{tc(`language_names.${code}`)}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {t('language_step.source_language')}
                </label>
                <select
                  value={values.source_language}
                  onChange={(e) => {
                    const code = e.target.value
                    setValues((v) => ({
                      ...v,
                      source_language: code,
                      source_language_name: tc(`language_names.${code}`).replace(/\s*\([a-z]+\)\s*$/, ''),
                    }))
                  }}
                  className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
                  style={inputStyle}
                >
                  {SOURCE_LANG_CODES.map((code) => (
                    <option key={code} value={code}>{tc(`language_names.${code}`)}</option>
                  ))}
                </select>
              </div>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                {t('language_step.help')}
              </p>
            </div>
          )}

          {currentStepDef.id === 'providers' && (
            <div className="space-y-4">
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {t('providers_step.info')}
              </p>
              <Field label={t('providers_step.opensubtitles_api_key')} type="password" {...fieldFor('opensubtitles_api_key')} />
              <Field label={t('providers_step.jimaku_api_key')} type="password" {...fieldFor('jimaku_api_key')} />
              <Field label={t('providers_step.subdl_api_key')} type="password" {...fieldFor('subdl_api_key')} />
            </div>
          )}

          {currentStepDef.id === 'automation' && (
            <div className="space-y-4">
              {/* Automatic subtitle search toggle */}
              <div
                className="flex items-start gap-3 p-3 rounded-lg"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
              >
                <input
                  type="checkbox"
                  id="automation_enabled"
                  checked={values.automation_enabled === 'true'}
                  onChange={(e) => set('automation_enabled', e.target.checked ? 'true' : 'false')}
                  className="mt-0.5 h-4 w-4 rounded"
                  style={{ accentColor: 'var(--accent)' }}
                />
                <div className="flex-1 space-y-1">
                  <label htmlFor="automation_enabled" className="block text-sm font-medium cursor-pointer" style={{ color: 'var(--text-primary)' }}>
                    {t('automation_step.auto_search_label')}
                  </label>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {t('automation_step.auto_search_description')}
                  </p>
                </div>
              </div>

              {/* Interval select — only shown when automation enabled */}
              {values.automation_enabled === 'true' && (
                <div className="space-y-1.5">
                  <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {t('automation_step.interval_label')}
                  </label>
                  <select
                    value={values.search_interval_hours}
                    onChange={(e) => set('search_interval_hours', e.target.value)}
                    className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
                    style={inputStyle}
                  >
                    <option value="1">{t('automation_step.interval_1h')}</option>
                    <option value="3">{t('automation_step.interval_3h')}</option>
                    <option value="6">{t('automation_step.interval_6h')}</option>
                    <option value="12">{t('automation_step.interval_12h')}</option>
                    <option value="24">{t('automation_step.interval_24h')}</option>
                  </select>
                </div>
              )}

              {/* Upgrade existing subtitles toggle */}
              <div
                className="flex items-start gap-3 p-3 rounded-lg"
                style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
              >
                <input
                  type="checkbox"
                  id="upgrade_enabled"
                  checked={values.upgrade_enabled === 'true'}
                  onChange={(e) => set('upgrade_enabled', e.target.checked ? 'true' : 'false')}
                  className="mt-0.5 h-4 w-4 rounded"
                  style={{ accentColor: 'var(--accent)' }}
                />
                <div className="flex-1 space-y-1">
                  <label htmlFor="upgrade_enabled" className="block text-sm font-medium cursor-pointer" style={{ color: 'var(--text-primary)' }}>
                    {t('automation_step.upgrade_label')}
                  </label>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {t('automation_step.upgrade_description')}
                  </p>
                </div>
              </div>

              {/* Info box */}
              <div
                className="flex items-start gap-2 p-3 rounded-lg text-xs"
                style={{ backgroundColor: 'var(--accent-bg)', border: '1px solid var(--accent-dim)', color: 'var(--text-secondary)' }}
              >
                <Zap size={12} className="mt-0.5 shrink-0" style={{ color: 'var(--accent)' }} />
                <span>{t('automation_step.settings_hint')}</span>
              </div>
            </div>
          )}

          {currentStepDef.id === 'ollama' && (
            <div className="space-y-4">
              <Field label={t('ollama_step.url')} placeholder="http://localhost:11434" {...fieldFor('ollama_url')} />
              <Field label={t('ollama_step.model')} placeholder="qwen2.5:14b-instruct" {...fieldFor('ollama_model')} />
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                {t('ollama_step.languages_hint', { source: values.source_language_name, target: values.target_language_name })}
              </p>
              <button
                onClick={testOllama}
                disabled={testing === 'ollama'}
                className="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
                style={{
                  border: '1px solid var(--border)',
                  color: 'var(--text-secondary)',
                  backgroundColor: 'var(--bg-primary)',
                }}
              >
                {testing === 'ollama' ? <Loader2 size={14} className="animate-spin" /> : <Cpu size={14} />}
                {t('ollama_step.test_connection')}
              </button>
            </div>
          )}

          {currentStepDef.id === 'mediaservers' && (
            <div className="space-y-4">
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {t('mediaservers_step.info')}
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
                const uid = msInstanceIds.current[idx] ?? `idx-${idx}`
                const testResult = msTestResults[uid]

                return (
                  <div
                    key={uid}
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
                      placeholder={t('mediaservers_step.server_name')}
                      className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
                      style={inputStyle}
                    />

                    {/* Dynamic config fields */}
                    {typeInfo?.config_fields.map((field) => {
                      const pwKey = `${uid}-${field.key}`
                      return (
                        <div key={field.key} className="space-y-1">
                          <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                            {field.label} {field.required && <span style={{ color: 'var(--error)' }}>*</span>}
                          </label>
                          <div className="flex items-center gap-1.5">
                            <input
                              type={field.type === 'password' && !msShowPasswords[pwKey] ? 'password' : 'text'}
                              value={String(inst[field.key] ?? '')}
                              onChange={(e) => updateMsField(idx, field.key, e.target.value)}
                              placeholder={field.default || (field.required ? t('mediaservers_step.required') : t('mediaservers_step.optional'))}
                              autoComplete={field.type === 'password' ? 'new-password' : 'off'}
                              spellCheck={false}
                              className="flex-1 px-2.5 py-1.5 rounded text-sm focus:outline-none"
                              style={inputStyle}
                            />
                            {field.type === 'password' && (
                              <button
                                onClick={() => setMsShowPasswords((p) => ({ ...p, [pwKey]: !p[pwKey] }))}
                                className="p-1.5 rounded"
                                style={{ border: '1px solid var(--border)', color: 'var(--text-muted)', backgroundColor: 'var(--bg-primary)' }}
                              >
                                {msShowPasswords[pwKey] ? <EyeOff size={12} /> : <Eye size={12} />}
                              </button>
                            )}
                          </div>
                        </div>
                      )
                    })}

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
                        {t('common:actions.test')}
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

              {msInstances.length === 0 && msTypes.length === 0 && !msTypesError && (
                <div className="text-center py-4">
                  <Loader2 size={16} className="animate-spin mx-auto" style={{ color: 'var(--accent)' }} />
                </div>
              )}
              {msTypesError && (
                <div
                  className="flex items-center gap-2 p-3 rounded-lg text-xs"
                  style={{ backgroundColor: 'var(--error-bg, var(--bg-primary))', border: '1px solid var(--error)' }}
                >
                  <AlertCircle size={14} style={{ color: 'var(--error)' }} />
                  <span className="flex-1" style={{ color: 'var(--text-primary)' }}>
                    {t('mediaservers_step.types_load_failed')}
                  </span>
                  <button
                    type="button"
                    onClick={loadMsTypes}
                    className="px-2 py-1 rounded text-xs"
                    style={{ border: '1px solid var(--border)', color: 'var(--text-primary)', backgroundColor: 'var(--bg-primary)' }}
                  >
                    {tc('actions.retry')}
                  </button>
                </div>
              )}
            </div>
          )}

          {currentStepDef.id === 'scan' && (
            <div className="space-y-4 text-center">
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                {t('scan_step.info')}
              </p>
              {!scanStarted ? (
                <button
                  onClick={startScan}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-medium text-white"
                  style={{ backgroundColor: 'var(--accent)' }}
                >
                  <Play size={16} />
                  {t('scan_step.start_scan')}
                </button>
              ) : (
                <div className="flex items-center justify-center gap-2" style={{ color: 'var(--success)' }}>
                  <CheckCircle size={18} />
                  <span className="text-sm font-medium">{t('scan_step.scan_started')}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between">
          <button
            onClick={() => step > 0 ? setStep((s) => s - 1) : skipSetup()}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm"
            style={{ color: 'var(--text-muted)' }}
          >
            <ArrowLeft size={14} />
            {step > 0 ? t('navigation.back') : t('navigation.skip_setup')}
          </button>

          {step < visibleSteps.length - 1 ? (
            <button
              onClick={saveAndNext}
              disabled={saving || currentStepDef.id === 'mode'}
              className="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium text-white"
              style={{ backgroundColor: currentStepDef.id === 'mode' ? 'var(--text-muted)' : 'var(--accent)' }}
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : null}
              {currentStepDef.id === 'mediaservers' ? (msInstances.length > 0 ? t('navigation.save_next') : t('navigation.skip')) : t('navigation.next')}
              <ArrowRight size={14} />
            </button>
          ) : (
            <button
              onClick={finish}
              className="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium text-white"
              style={{ backgroundColor: 'var(--success)' }}
            >
              <CheckCircle size={14} />
              {t('navigation.finish')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
