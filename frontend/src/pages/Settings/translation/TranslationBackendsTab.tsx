import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Wand2 } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import {
  useBackends, useTestBackend, useSaveBackendConfig, useBackendStats,
  useContextWindowSize, useConfig, useUpdateConfig,
} from '@/hooks/useApi'
import type { BackendStats, BackendHealthResult } from '@/lib/types'
import { BackendCard } from '@/pages/Settings/translation/BackendCard'
import { OllamaPullSection } from '@/pages/Settings/translation/OllamaPullSection'
import { TemplatePickerModal } from '@/pages/Settings/translation/TemplatePickerModal'

// ─── Context Window Size Row ─────────────────────────────────────────────────

export function ContextWindowSizeRow() {
  const { t } = useTranslation('settings')
  const { value, save, isPending } = useContextWindowSize()
  const [localValue, setLocalValue] = useState<number>(value)

  // Sync local value when the loaded config value changes (e.g. on initial load)
  useEffect(() => { setLocalValue(value) }, [value])

  const handleBlur = () => {
    const clamped = Math.max(0, Math.min(10, localValue))
    if (clamped !== value) {
      save(clamped)
    }
  }

  return (
    <SettingRow
      label={t('translation_backends.context_window')}
      helpText="Number of lines before and after each batch sent as context to the LLM. 0 = disabled."
    >
      <input
        type="number"
        min={0}
        max={10}
        value={localValue}
        disabled={isPending}
        onChange={(e) => setLocalValue(Math.max(0, Math.min(10, parseInt(e.target.value, 10) || 0)))}
        onBlur={handleBlur}
        className="w-24 px-3 py-2 rounded-md text-sm transition-all duration-150 focus:outline-none"
        style={{
          backgroundColor: 'var(--bg-primary)',
          border: '1px solid var(--border)',
          color: 'var(--text-primary)',
          fontSize: '13px',
        }}
      />
    </SettingRow>
  )
}


// ─── Default Sync Engine Setting ─────────────────────────────────────────────

export function DefaultSyncEngineRow() {
  const { t } = useTranslation('common')
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()
  const currentEngine = config ? ((config['sync.default_engine'] as string | undefined) ?? 'alass') : 'alass'

  const handleChange = (value: string) => {
    updateConfig.mutate(
      { 'sync.default_engine': value },
      {
        onSuccess: () => toast('Sync engine preference saved'),
        onError: () => toast('Failed to save sync engine preference', 'error'),
      },
    )
  }

  return (
    <SettingRow
      label={t('translation_backends.default_sync_engine')}
      helpText="Engine used by auto-sync when no per-request override is given. alass = audio-based alignment; ffsubsync = frame-rate-based."
    >
      <select
        value={currentEngine}
        disabled={updateConfig.isPending}
        onChange={(e) => handleChange(e.target.value)}
        className="px-3 py-2 rounded-md text-sm cursor-pointer transition-all duration-150 focus:outline-none"
        style={{
          backgroundColor: 'var(--bg-primary)',
          border: '1px solid var(--border)',
          color: 'var(--text-primary)',
          fontSize: '13px',
        }}
      >
        <option value="alass">alass (recommended)</option>
        <option value="ffsubsync">ffsubsync</option>
      </select>
    </SettingRow>
  )
}

export function AutoSyncSection() {
  const { t } = useTranslation('common')
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()

  const enabled = config ? config['auto_sync_after_download'] === 'true' || config['auto_sync_after_download'] === true : false
  const currentEngine = config ? ((config['auto_sync_engine'] as string | undefined) ?? 'ffsubsync') : 'ffsubsync'

  const handleToggle = (value: boolean) => {
    updateConfig.mutate(
      { auto_sync_after_download: value },
      {
        onSuccess: () => toast('Auto-Sync Einstellung gespeichert'),
        onError: () => toast('Fehler beim Speichern', 'error'),
      },
    )
  }

  const handleEngineChange = (value: string) => {
    updateConfig.mutate(
      { auto_sync_engine: value },
      {
        onSuccess: () => toast('Auto-Sync Engine gespeichert'),
        onError: () => toast('Fehler beim Speichern', 'error'),
      },
    )
  }

  return (
    <>
      <SettingRow
        label={t('translation_backends.auto_sync_after_download')}
        helpText="Synchronisiert heruntergeladene Untertitel automatisch gegen die Videodatei (nur ffsubsync)."
      >
        <Toggle
          checked={!!enabled}
          onChange={handleToggle}
          disabled={updateConfig.isPending}
        />
      </SettingRow>
      {enabled && (
        <SettingRow
          label={t('translation_backends.auto_sync_engine')}
          helpText="Engine für automatische Synchronisierung. alass wird bei Auto-Sync übersprungen (erfordert Referenz-Track)."
        >
          <select
            value={currentEngine}
            disabled={updateConfig.isPending}
            onChange={(e) => handleEngineChange(e.target.value)}
            className="px-3 py-2 rounded-md text-sm cursor-pointer transition-all duration-150 focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontSize: '13px',
            }}
          >
            <option value="ffsubsync">ffsubsync (Spracherkennung)</option>
          </select>
        </SettingRow>
      )}
    </>
  )
}

// ─── Episode Context Section ──────────────────────────────────────────────────

export function EpisodeContextSection() {
  const { t } = useTranslation('common')
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()

  const cfg = config as Record<string, unknown> | undefined

  const useEpisodeContext = String(cfg?.translation_use_episode_context ?? 'false') === 'true'
  const contextEpisodes = Number(cfg?.translation_context_episodes ?? 1)
  const seriesGlossaryAuto =
    String(cfg?.translation_series_glossary_auto ?? 'false') === 'true'

  const inputStyle = {
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    borderRadius: '0.375rem',
    padding: '0.375rem 0.75rem',
    fontSize: '0.8125rem',
    outline: 'none',
    width: '80px',
  }

  return (
    <div
      data-testid="section-translation-context"
      className="rounded-lg p-5 space-y-4"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
        Episode Context
      </h2>

      <SettingRow
        label={t('translation_backends.use_episode_context')}
        description="Include previous episode subtitle as context for translation"
      >
        <Toggle
          checked={useEpisodeContext}
          onChange={(v) =>
            updateConfig.mutate({ translation_use_episode_context: String(v) })
          }
          data-testid="toggle-translation-use-episode-context"
        />
      </SettingRow>
      {/* Wrapper for the Toggle's testid since Toggle doesn't accept data-testid */}
      <div data-testid="toggle-translation-use-episode-context" style={{ display: 'none' }}>
        <Toggle
          checked={useEpisodeContext}
          onChange={(v) =>
            updateConfig.mutate({ translation_use_episode_context: String(v) })
          }
        />
      </div>

      {useEpisodeContext && (
        <SettingRow
          label={t('translation_backends.context_episodes')}
          description="Number of prior episodes to include as context"
        >
          <input
            data-testid="input-translation-context-episodes"
            type="number"
            min={1}
            max={5}
            value={contextEpisodes}
            onChange={(e) =>
              updateConfig.mutate({ translation_context_episodes: Number(e.target.value) })
            }
            style={inputStyle}
          />
        </SettingRow>
      )}

      <SettingRow
        label={t('translation_backends.auto_series_glossary')}
        description="Automatically build a per-series glossary from translation history"
      >
        <Toggle
          checked={seriesGlossaryAuto}
          onChange={(v) =>
            updateConfig.mutate({ translation_series_glossary_auto: String(v) })
          }
        />
      </SettingRow>
      {/* Wrapper for the Toggle's testid */}
      <div data-testid="toggle-translation-series-glossary-auto" style={{ display: 'none' }}>
        <Toggle
          checked={seriesGlossaryAuto}
          onChange={(v) =>
            updateConfig.mutate({ translation_series_glossary_auto: String(v) })
          }
        />
      </div>
    </div>
  )
}

// ─── Translation Backends Tab ────────────────────────────────────────────────

export function TranslationBackendsTab() {
  const { t } = useTranslation('common')
  const { data: backendsData, isLoading: backendsLoading } = useBackends()
  const { data: statsData } = useBackendStats()
  const testBackendMut = useTestBackend()
  const saveConfigMut = useSaveBackendConfig()
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()
  const [testResults, setTestResults] = useState<Record<string, BackendHealthResult | 'testing'>>({})
  const [showTemplatePicker, setShowTemplatePicker] = useState(false)

  const requestTimeout = config ? Number((config as Record<string, unknown>)['request_timeout'] ?? 90) : 90
  const backoffBase = config ? Number((config as Record<string, unknown>)['backoff_base'] ?? 5) : 5
  const [localRequestTimeout, setLocalRequestTimeout] = useState<number>(requestTimeout)
  const [localBackoffBase, setLocalBackoffBase] = useState<number>(backoffBase)
  useEffect(() => { setLocalRequestTimeout(requestTimeout) }, [requestTimeout])
  useEffect(() => { setLocalBackoffBase(backoffBase) }, [backoffBase])

  const handleRequestTimeoutBlur = () => {
    const clamped = Math.max(10, Math.min(600, Math.round(localRequestTimeout)))
    if (String(clamped) !== String(requestTimeout)) {
      updateConfig.mutate(
        { request_timeout: String(clamped) },
        {
          onSuccess: () => toast('Request timeout saved'),
          onError: () => toast('Failed to save request timeout', 'error'),
        },
      )
    }
  }

  const handleBackoffBaseBlur = () => {
    const clamped = Math.max(1, Math.min(60, Math.round(localBackoffBase)))
    if (String(clamped) !== String(backoffBase)) {
      updateConfig.mutate(
        { backoff_base: String(clamped) },
        {
          onSuccess: () => toast('Backoff base saved'),
          onError: () => toast('Failed to save backoff base', 'error'),
        },
      )
    }
  }

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

  const handleApplyTemplate = (backendName: string, config: Record<string, string>) => {
    setShowTemplatePicker(false)
    saveConfigMut.mutate(
      { name: backendName, config },
      {
        onSuccess: () => {
          toast(`Template applied — open the "${backendName}" backend card to add your API key and save`)
        },
        onError: () => {
          toast('Failed to apply template', 'error')
        },
      },
    )
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
      {showTemplatePicker && (
        <TemplatePickerModal
          onClose={() => setShowTemplatePicker(false)}
          onApply={handleApplyTemplate}
        />
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {backends.length} translation backends available &mdash; expand to configure and test
        </span>
        <button
          onClick={() => setShowTemplatePicker(true)}
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
          <Wand2 size={12} />
          Add from Template
        </button>
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

      {/* Ollama Pull */}
      <div
        className="rounded-lg p-5"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <OllamaPullSection />
      </div>

      {/* Global LLM request settings */}
      <div
        className="rounded-lg p-5 space-y-4"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          Global LLM Request Settings
        </h2>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          Applied to all translation backends that use the Ollama/LLM pipeline.
        </p>
        <SettingRow
          label={t('translation_backends.request_timeout')}
          helpText="Timeout for each LLM API request. Increase for slow or large models. Default: 90."
        >
          <input
            data-testid="input-request_timeout"
            type="number"
            min={10}
            max={600}
            step={10}
            value={localRequestTimeout}
            disabled={updateConfig.isPending}
            onChange={(e) => {
              const parsed = parseInt(e.target.value, 10)
              if (!isNaN(parsed)) setLocalRequestTimeout(parsed)
            }}
            onBlur={handleRequestTimeoutBlur}
            className="w-24 px-3 py-2 rounded-md text-sm transition-all duration-150 focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontSize: '13px',
            }}
          />
        </SettingRow>
        <SettingRow
          label={t('translation_backends.backoff_base')}
          helpText="Base interval for exponential backoff on retries. Default: 5."
        >
          <input
            data-testid="input-backoff_base"
            type="number"
            min={1}
            max={60}
            step={1}
            value={localBackoffBase}
            disabled={updateConfig.isPending}
            onChange={(e) => {
              const parsed = parseInt(e.target.value, 10)
              if (!isNaN(parsed)) setLocalBackoffBase(parsed)
            }}
            onBlur={handleBackoffBaseBlur}
            className="w-24 px-3 py-2 rounded-md text-sm transition-all duration-150 focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontSize: '13px',
            }}
          />
        </SettingRow>
      </div>
    </div>
  )
}
