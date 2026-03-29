/**
 * ConnectionsSettings — settings detail page for all external service connections.
 *
 * Sections:
 * 1. Sonarr Connection   — multi-instance (sonarr_instances_json)
 * 2. Radarr Connection   — multi-instance (radarr_instances_json)
 * 3. Media Servers
 * 4. API Keys
 * 5. Metadata API Keys   — TMDB, TheTVDB, cache TTL, ffmpeg_timeout
 */
import { useState, lazy, Suspense } from 'react'

function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}
import { useTranslation } from 'react-i18next'
import { Link, PlugZap, Server, Loader2, Plus, Pencil, TestTube, Trash2, Eye, EyeOff, Database } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import {
  useConfig, useUpdateConfig,
  useTestSonarrInstance, useTestRadarrInstance,
} from '@/hooks/useApi'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'

// ─── Lazy imports for heavier sub-tabs ───────────────────────────────────────
const MediaServersTab = lazy(() => import('./MediaServersTab').then(m => ({ default: m.MediaServersTab })))

function TabSkeleton() {
  return (
    <div className="flex items-center justify-center h-16">
      <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
    </div>
  )
}

// ─── Multi-instance types ─────────────────────────────────────────────────────

interface ServiceInstance {
  id: string
  name: string
  url: string
  api_key: string
}

type InstanceStatus = 'unconfigured' | 'connected' | 'error'

interface InstanceState {
  status: InstanceStatus
  message: string | null
  testing: boolean
}

// ─── Multi-instance helpers ───────────────────────────────────────────────────

function parseInstances(json: unknown): ServiceInstance[] {
  if (!json || typeof json !== 'string' || !json.trim()) return []
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (item): item is ServiceInstance =>
        typeof item === 'object' &&
        item !== null &&
        typeof item.id === 'string' &&
        typeof item.name === 'string' &&
        typeof item.url === 'string' &&
        typeof item.api_key === 'string',
    )
  } catch {
    return []
  }
}

function serializeInstances(instances: ServiceInstance[]): string {
  return JSON.stringify(instances)
}

// ─── InstanceCard sub-component ──────────────────────────────────────────────

interface InstanceCardProps {
  prefix: string
  inst: ServiceInstance
  state: InstanceState
  editingName: string | null
  placeholder: string
  onEditName: (id: string) => void
  onNameChange: (name: string) => void
  onNameBlur: () => void
  onUrlChange: (url: string) => void
  onApiKeyChange: (key: string) => void
  onTest: () => void
  onRemove: () => void
}

function InstanceCard({
  prefix,
  inst,
  state,
  editingName,
  placeholder,
  onEditName,
  onNameChange,
  onNameBlur,
  onUrlChange,
  onApiKeyChange,
  onTest,
  onRemove,
}: InstanceCardProps) {
  const [showKey, setShowKey] = useState(false)

  const statusColor: Record<InstanceStatus, string> = {
    connected: 'var(--success)',
    error: 'var(--error)',
    unconfigured: 'var(--text-muted)',
  }

  const inputStyle = {
    backgroundColor: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    fontSize: '12px',
    padding: '6px 10px',
    borderRadius: '6px',
  } as const

  return (
    <div
      data-testid={`${prefix}-instance-card-${inst.id}`}
      className="rounded-lg overflow-hidden"
      style={{ border: '1px solid var(--border)', backgroundColor: 'var(--bg-surface)' }}
    >
      {/* Card header row */}
      <div className="flex items-center gap-3 px-3 py-2.5">
        {/* Status dot */}
        <div
          data-testid={`${prefix}-instance-status-dot-${inst.id}`}
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: statusColor[state.status] }}
        />

        {/* Name — inline edit on pencil click */}
        {editingName === inst.id ? (
          <input
            data-testid={`${prefix}-instance-name-input-${inst.id}`}
            type="text"
            value={inst.name}
            onChange={(e) => onNameChange(e.target.value)}
            onBlur={onNameBlur}
            autoFocus
            className="flex-1 text-sm font-medium focus:outline-none rounded px-1"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--accent-dim)',
              color: 'var(--text-primary)',
            }}
          />
        ) : (
          <div className="flex items-center gap-1.5 flex-1 min-w-0 group">
            <span
              className="text-sm font-medium truncate"
              style={{ color: 'var(--text-primary)' }}
            >
              {inst.name}
            </span>
            <button
              data-testid={`${prefix}-instance-edit-name-btn-${inst.id}`}
              type="button"
              onClick={() => onEditName(inst.id)}
              className="opacity-0 group-hover:opacity-100 p-0.5 rounded transition-opacity"
              style={{ color: 'var(--text-muted)' }}
            >
              <Pencil size={11} />
            </button>
          </div>
        )}

        {/* Test button */}
        <button
          data-testid={`${prefix}-instance-test-btn-${inst.id}`}
          type="button"
          onClick={onTest}
          disabled={state.testing || !inst.url.trim()}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs transition-all duration-150"
          style={{
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-primary)',
            opacity: (state.testing || !inst.url.trim()) ? 0.5 : 1,
          }}
        >
          {state.testing
            ? <Loader2 size={11} className="animate-spin" />
            : <TestTube size={11} />}
          Test
        </button>

        {/* Remove button */}
        <button
          data-testid={`${prefix}-instance-remove-btn-${inst.id}`}
          type="button"
          onClick={onRemove}
          className="p-1.5 rounded transition-colors"
          style={{ color: 'var(--text-muted)' }}
          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
        >
          <Trash2 size={13} />
        </button>
      </div>

      {/* Test result message */}
      {state.message && (
        <div
          className="px-3 pb-1.5 text-[11px]"
          style={{ color: state.status === 'connected' ? 'var(--success)' : 'var(--error)' }}
        >
          {state.message}
        </div>
      )}

      {/* URL + API Key fields */}
      <div
        className="px-3 pb-3 space-y-2"
        style={{ borderTop: '1px solid var(--border)', paddingTop: '10px' }}
      >
        <input
          data-testid={`${prefix}-instance-url-input-${inst.id}`}
          type="text"
          value={inst.url}
          onChange={(e) => onUrlChange(e.target.value)}
          placeholder={placeholder}
          className="w-full focus:outline-none"
          style={inputStyle}
        />
        <div className="flex items-center gap-1.5">
          <input
            data-testid={`${prefix}-instance-apikey-input-${inst.id}`}
            type={showKey ? 'text' : 'password'}
            value={inst.api_key}
            onChange={(e) => onApiKeyChange(e.target.value)}
            placeholder="API Key"
            className="flex-1 focus:outline-none"
            style={inputStyle}
          />
          <button
            type="button"
            onClick={() => setShowKey((v) => !v)}
            className="p-1.5 rounded"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-primary)',
            }}
          >
            {showKey ? <EyeOff size={12} /> : <Eye size={12} />}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Sonarr Multi-Instance Section ───────────────────────────────────────────

function SonarrMultiInstanceSection() {
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()
  const testSonarr = useTestSonarrInstance()

  const cfg = configData as Record<string, unknown> | undefined

  const [instances, setInstances] = useState<ServiceInstance[]>(() =>
    parseInstances(cfg?.sonarr_instances_json),
  )
  const [statuses, setStatuses] = useState<Record<string, InstanceState>>({})
  const [editingName, setEditingName] = useState<string | null>(null)

  const persist = (next: ServiceInstance[]) => {
    setInstances(next)
    updateConfig.mutate({ sonarr_instances_json: serializeInstances(next) })
  }

  const addInstance = () => {
    const newInst: ServiceInstance = {
      id: generateId(),
      name: `Sonarr ${instances.length + 1}`,
      url: '',
      api_key: '',
    }
    persist([...instances, newInst])
  }

  const removeInstance = (id: string) => {
    persist(instances.filter((inst) => inst.id !== id))
    setStatuses((prev) => {
      const { [id]: _, ...rest } = prev
      return rest
    })
  }

  const updateInstance = (id: string, patch: Partial<ServiceInstance>) => {
    persist(instances.map((inst) => (inst.id === id ? { ...inst, ...patch } : inst)))
  }

  const testInstance = (inst: ServiceInstance) => {
    if (!inst.url.trim()) return
    setStatuses((prev) => ({
      ...prev,
      [inst.id]: { status: 'unconfigured', message: null, testing: true },
    }))
    testSonarr.mutate(
      { url: inst.url.trim(), api_key: inst.api_key.trim() },
      {
        onSuccess: (result) => {
          setStatuses((prev) => ({
            ...prev,
            [inst.id]: {
              status: result.healthy ? 'connected' : 'error',
              message: result.message,
              testing: false,
            },
          }))
        },
        onError: () => {
          setStatuses((prev) => ({
            ...prev,
            [inst.id]: { status: 'error', message: 'Connection failed', testing: false },
          }))
        },
      },
    )
  }

  return (
    <div data-testid="sonarr-multi-instance" className="space-y-2">
      {instances.map((inst) => {
        const state = statuses[inst.id] ?? { status: 'unconfigured', message: null, testing: false }
        return (
          <InstanceCard
            key={inst.id}
            prefix="sonarr"
            inst={inst}
            state={state}
            editingName={editingName}
            placeholder="http://localhost:8989"
            onEditName={(id) => setEditingName(id)}
            onNameChange={(name) => updateInstance(inst.id, { name })}
            onNameBlur={() => setEditingName(null)}
            onUrlChange={(url) => updateInstance(inst.id, { url })}
            onApiKeyChange={(api_key) => updateInstance(inst.id, { api_key })}
            onTest={() => testInstance(inst)}
            onRemove={() => removeInstance(inst.id)}
          />
        )
      })}

      {/* Add instance */}
      <button
        data-testid="sonarr-add-instance-btn"
        type="button"
        onClick={addInstance}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-medium transition-colors duration-150"
        style={{
          border: '1px dashed var(--border)',
          color: 'var(--text-muted)',
          backgroundColor: 'transparent',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = 'var(--accent-dim)'
          e.currentTarget.style.color = 'var(--accent)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = 'var(--border)'
          e.currentTarget.style.color = 'var(--text-muted)'
        }}
      >
        <Plus size={12} />
        Add instance
      </button>
    </div>
  )
}

// ─── Radarr Multi-Instance Section ───────────────────────────────────────────

function RadarrMultiInstanceSection() {
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()
  const testRadarr = useTestRadarrInstance()

  const cfg = configData as Record<string, unknown> | undefined

  const [instances, setInstances] = useState<ServiceInstance[]>(() =>
    parseInstances(cfg?.radarr_instances_json),
  )
  const [statuses, setStatuses] = useState<Record<string, InstanceState>>({})
  const [editingName, setEditingName] = useState<string | null>(null)

  const persist = (next: ServiceInstance[]) => {
    setInstances(next)
    updateConfig.mutate({ radarr_instances_json: serializeInstances(next) })
  }

  const addInstance = () => {
    const newInst: ServiceInstance = {
      id: generateId(),
      name: `Radarr ${instances.length + 1}`,
      url: '',
      api_key: '',
    }
    persist([...instances, newInst])
  }

  const removeInstance = (id: string) => {
    persist(instances.filter((inst) => inst.id !== id))
    setStatuses((prev) => {
      const { [id]: _, ...rest } = prev
      return rest
    })
  }

  const updateInstance = (id: string, patch: Partial<ServiceInstance>) => {
    persist(instances.map((inst) => (inst.id === id ? { ...inst, ...patch } : inst)))
  }

  const testInstance = (inst: ServiceInstance) => {
    if (!inst.url.trim()) return
    setStatuses((prev) => ({
      ...prev,
      [inst.id]: { status: 'unconfigured', message: null, testing: true },
    }))
    testRadarr.mutate(
      { url: inst.url.trim(), api_key: inst.api_key.trim() },
      {
        onSuccess: (result) => {
          setStatuses((prev) => ({
            ...prev,
            [inst.id]: {
              status: result.healthy ? 'connected' : 'error',
              message: result.message,
              testing: false,
            },
          }))
        },
        onError: () => {
          setStatuses((prev) => ({
            ...prev,
            [inst.id]: { status: 'error', message: 'Connection failed', testing: false },
          }))
        },
      },
    )
  }

  return (
    <div data-testid="radarr-multi-instance" className="space-y-2">
      {instances.map((inst) => {
        const state = statuses[inst.id] ?? { status: 'unconfigured', message: null, testing: false }
        return (
          <InstanceCard
            key={inst.id}
            prefix="radarr"
            inst={inst}
            state={state}
            editingName={editingName}
            placeholder="http://localhost:7878"
            onEditName={(id) => setEditingName(id)}
            onNameChange={(name) => updateInstance(inst.id, { name })}
            onNameBlur={() => setEditingName(null)}
            onUrlChange={(url) => updateInstance(inst.id, { url })}
            onApiKeyChange={(api_key) => updateInstance(inst.id, { api_key })}
            onTest={() => testInstance(inst)}
            onRemove={() => removeInstance(inst.id)}
          />
        )
      })}

      {/* Add instance */}
      <button
        data-testid="radarr-add-instance-btn"
        type="button"
        onClick={addInstance}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-medium transition-colors duration-150"
        style={{
          border: '1px dashed var(--border)',
          color: 'var(--text-muted)',
          backgroundColor: 'transparent',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = 'var(--accent-dim)'
          e.currentTarget.style.color = 'var(--accent)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = 'var(--border)'
          e.currentTarget.style.color = 'var(--text-muted)'
        }}
      >
        <Plus size={12} />
        Add instance
      </button>
    </div>
  )
}

// ─── Metadata API Keys Section ────────────────────────────────────────────────

interface MetadataApiKeysSectionProps {
  ffmpegTimeout: string
}

function MetadataApiKeysSection({ ffmpegTimeout }: MetadataApiKeysSectionProps) {
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()

  const cfg = configData as Record<string, unknown> | undefined

  const [tmdbKey, setTmdbKey] = useState(() => String(cfg?.tmdb_api_key ?? ''))
  const [tvdbKey, setTvdbKey] = useState(() => String(cfg?.tvdb_api_key ?? ''))
  const [tvdbPin, setTvdbPin] = useState(() => String(cfg?.tvdb_pin ?? ''))
  const [cacheTtl, setCacheTtl] = useState(() => String(cfg?.metadata_cache_ttl_days ?? '7'))

  const [showTmdb, setShowTmdb] = useState(false)
  const [showTvdb, setShowTvdb] = useState(false)
  const [showPin, setShowPin]   = useState(false)

  const handleSave = () => {
    updateConfig.mutate(
      {
        tmdb_api_key:            tmdbKey,
        tvdb_api_key:            tvdbKey,
        tvdb_pin:                tvdbPin,
        metadata_cache_ttl_days: cacheTtl,
        ffmpeg_timeout:          ffmpegTimeout,
      },
      {
        onSuccess: () => toast('Metadata settings saved'),
        onError:   () => toast('Failed to save metadata settings', 'error'),
      },
    )
  }

  const inputStyle = {
    backgroundColor: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
    padding: '7px 12px',
    borderRadius: '6px',
    flex: 1,
  } as const

  const numberInputStyle = {
    ...inputStyle,
    width: '120px',
    flex: 'none',
  } as const

  return (
    <div data-testid="metadata-api-keys-section" className="space-y-0">

      {/* TMDB */}
      <div
        className="flex items-center justify-between py-3"
        style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}
      >
        <label
          htmlFor="tmdb-api-key"
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          TMDB API Key
        </label>
        <div className="flex items-center gap-1.5">
          <input
            id="tmdb-api-key"
            data-testid="metadata-tmdb-api-key"
            type={showTmdb ? 'text' : 'password'}
            value={tmdbKey}
            onChange={(e) => setTmdbKey(e.target.value)}
            placeholder="Enter TMDB v3 API key"
            className="focus:outline-none"
            style={{ ...inputStyle, width: '260px' }}
          />
          <button
            type="button"
            onClick={() => setShowTmdb((v) => !v)}
            className="p-1.5 rounded"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-primary)',
            }}
          >
            {showTmdb ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
      </div>

      {/* TVDB API Key */}
      <div
        className="flex items-center justify-between py-3"
        style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}
      >
        <label
          htmlFor="tvdb-api-key"
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          TheTVDB API Key
        </label>
        <div className="flex items-center gap-1.5">
          <input
            id="tvdb-api-key"
            data-testid="metadata-tvdb-api-key"
            type={showTvdb ? 'text' : 'password'}
            value={tvdbKey}
            onChange={(e) => setTvdbKey(e.target.value)}
            placeholder="Enter TheTVDB v4 API key"
            className="focus:outline-none"
            style={{ ...inputStyle, width: '260px' }}
          />
          <button
            type="button"
            onClick={() => setShowTvdb((v) => !v)}
            className="p-1.5 rounded"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-primary)',
            }}
          >
            {showTvdb ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
      </div>

      {/* TVDB PIN */}
      <div
        className="flex items-center justify-between py-3"
        style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}
      >
        <label
          htmlFor="tvdb-pin"
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          TheTVDB PIN
        </label>
        <div className="flex items-center gap-1.5">
          <input
            id="tvdb-pin"
            data-testid="metadata-tvdb-pin"
            type={showPin ? 'text' : 'password'}
            value={tvdbPin}
            onChange={(e) => setTvdbPin(e.target.value)}
            placeholder="Optional subscriber PIN"
            className="focus:outline-none"
            style={{ ...inputStyle, width: '260px' }}
          />
          <button
            type="button"
            onClick={() => setShowPin((v) => !v)}
            className="p-1.5 rounded"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-primary)',
            }}
          >
            {showPin ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
      </div>

      {/* Metadata cache TTL */}
      <div className="flex items-center justify-between py-3">
        <div className="flex flex-col gap-0.5">
          <label
            htmlFor="metadata-cache-ttl"
            className="text-[13px] font-medium"
            style={{ color: 'var(--text-primary)' }}
          >
            Cache TTL (days)
          </label>
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            How long metadata is cached before a refresh.
          </span>
        </div>
        <input
          id="metadata-cache-ttl"
          data-testid="metadata-cache-ttl"
          type="number"
          min={1}
          value={cacheTtl}
          onChange={(e) => setCacheTtl(e.target.value)}
          className="focus:outline-none"
          style={numberInputStyle}
        />
      </div>

      {/* Save */}
      <div className="flex justify-end pt-2">
        <button
          data-testid="metadata-save-btn"
          type="button"
          onClick={handleSave}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          Save
        </button>
      </div>

      {/* ffmpeg_timeout — exposed via advanced prop in parent SettingsSection */}
      {/* rendered by the wrapping SettingsSection's advanced={} prop */}
    </div>
  )
}

// ─── ffmpeg timeout inline JSX (used as advanced prop) ───────────────────────

function FfmpegTimeoutField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div data-testid="metadata-advanced-content" className="space-y-3">
      <div className="flex items-center justify-between py-2">
        <div className="flex flex-col gap-0.5">
          <label
            htmlFor="ffmpeg-timeout"
            className="text-[13px] font-medium"
            style={{ color: 'var(--text-primary)' }}
          >
            FFmpeg Timeout (seconds)
          </label>
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            Maximum time for ffprobe/ffmpeg operations.
          </span>
        </div>
        <input
          id="ffmpeg-timeout"
          data-testid="metadata-ffmpeg-timeout"
          type="number"
          min={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="focus:outline-none"
          style={{
            width: '100px',
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
            fontSize: '13px',
            padding: '7px 12px',
            borderRadius: '6px',
          }}
        />
      </div>
    </div>
  )
}

// ─── MetadataSection wrapper (owns ffmpegTimeout state for advanced prop) ────

function MetadataSectionWrapper() {
  const { data: configData } = useConfig()
  const cfg = configData as Record<string, unknown> | undefined
  const [ffmpegTimeout, setFfmpegTimeout] = useState(() => String(cfg?.ffmpeg_timeout ?? '30'))
  const updateConfig = useUpdateConfig()

  const handleFfmpegSave = (v: string) => {
    setFfmpegTimeout(v)
    updateConfig.mutate({ ffmpeg_timeout: v })
  }

  return (
    <SettingsSection
      title="Metadata API Keys"
      description="API keys for metadata providers (TMDB, TheTVDB) and media tooling"
      icon={<Database size={16} style={{ color: 'var(--accent)' }} />}
      advanced={<FfmpegTimeoutField value={ffmpegTimeout} onChange={handleFfmpegSave} />}
    >
      <div className="py-1">
        <MetadataApiKeysSection ffmpegTimeout={ffmpegTimeout} />
      </div>
    </SettingsSection>
  )
}

// ─── Main ConnectionsSettings Page ───────────────────────────────────────────

export function ConnectionsSettings() {
  const { t } = useTranslation('common')

  return (
    <SettingsDetailLayout
      title="Connections"
      subtitle="Configure external service integrations"
      breadcrumb={[
        { label: t('settings.breadcrumb.settings', 'Settings'), href: '/settings' },
        { label: 'Connections' },
      ]}
    >
      {/* Sonarr */}
      <SettingsSection
        data-testid="sonarr-section"
        title="Sonarr"
        description="TV series library management and download client integration"
        icon={<Link size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-3">
          <SonarrMultiInstanceSection />
        </div>
      </SettingsSection>

      {/* Radarr */}
      <SettingsSection
        data-testid="radarr-section"
        title="Radarr"
        description="Movie library management and download client integration"
        icon={<PlugZap size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-3">
          <RadarrMultiInstanceSection />
        </div>
      </SettingsSection>

      {/* Media Servers */}
      <SettingsSection
        data-testid="media-servers-section"
        title="Media Servers"
        description="Jellyfin, Plex, and Kodi instances for library refresh notifications"
        icon={<Server size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-3">
          <Suspense fallback={<TabSkeleton />}>
            <MediaServersTab />
          </Suspense>
        </div>
      </SettingsSection>

      {/* Metadata API Keys */}
      <MetadataSectionWrapper />
    </SettingsDetailLayout>
  )
}
