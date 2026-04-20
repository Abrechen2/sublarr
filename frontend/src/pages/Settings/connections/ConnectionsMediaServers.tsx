/**
 * ConnectionsMediaServers — Sonarr and Radarr multi-instance configuration.
 *
 * Extracted from ConnectionsSettings.tsx (pure file split, no functional changes).
 * All config keys, design, and SettingsSection/FormGroup patterns are unchanged.
 */
import { useState, lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, PlugZap, Server, Loader2, Plus, Pencil, TestTube, Trash2, Eye, EyeOff, ScanLine } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import {
  useConfig, useUpdateConfig,
  useTestSonarrInstance, useTestRadarrInstance,
} from '@/hooks/useApi'
import { useStandaloneStatus, useTriggerStandaloneScan } from '@/hooks/useSystemApi'
import { SettingsSection } from '@/components/settings/SettingsSection'

// ─── Lazy imports for heavier sub-tabs ───────────────────────────────────────
const MediaServersTab = lazy(() => import('../MediaServersTab').then(m => ({ default: m.MediaServersTab })))
const StandaloneSettingsTab = lazy(() => import('../StandaloneSettingsTab').then(m => ({ default: m.StandaloneSettingsTab })))

function TabSkeleton() {
  return (
    <div className="flex items-center justify-center h-16">
      <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
    </div>
  )
}

// ─── Multi-instance types ─────────────────────────────────────────────────────

export interface ServiceInstance {
  id: string
  name: string
  url: string
  api_key: string
}

export type InstanceStatus = 'unconfigured' | 'connected' | 'error'

export interface InstanceState {
  status: InstanceStatus
  message: string | null
  testing: boolean
}

// ─── Multi-instance helpers ───────────────────────────────────────────────────

export function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

export function parseInstances(json: unknown): ServiceInstance[] {
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

export function serializeInstances(instances: ServiceInstance[]): string {
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
            placeholder={t('connections_media_servers.api_key')}
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

// ─── Standalone Section ───────────────────────────────────────────────────────

function StandaloneSection() {
  const { t } = useTranslation('settings')
  const { data: status } = useStandaloneStatus()
  const scan = useTriggerStandaloneScan()

  const isActive = status?.enabled ?? false
  const isAutoActivated = status?.auto_activated ?? false
  const isScanning = status?.scanner_scanning ?? false
  const foldersCount = status?.folders_count ?? 0

  function handleScan() {
    scan.mutate(undefined, {
      onSuccess: () => {
        toast(t('connections.standalone.scan_started'), 'success')
      },
      onError: () => {
        toast(t('connections.standalone.scan_failed'), 'error')
      },
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span
            className="text-sm font-medium px-2 py-0.5 rounded-full"
            style={{
              background: isActive
                ? 'color-mix(in srgb, var(--accent) 15%, transparent)'
                : 'color-mix(in srgb, var(--muted) 30%, transparent)',
              color: isActive ? 'var(--accent)' : 'var(--muted-foreground)',
            }}
          >
            {isAutoActivated ? t('connections.standalone.status_auto') : isActive ? t('connections.standalone.status_active') : t('connections.standalone.status_inactive')}
          </span>
          <span className="text-sm" style={{ color: 'var(--muted-foreground)' }}>
            {foldersCount > 0
              ? t('connections.standalone.folders_count', { count: foldersCount })
              : t('connections.standalone.no_folders')}
          </span>
        </div>

        <button
          onClick={handleScan}
          disabled={isScanning || scan.isPending}
          className="flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition-colors"
          style={{
            background: 'color-mix(in srgb, var(--accent) 12%, transparent)',
            color: 'var(--accent)',
            cursor: isScanning || scan.isPending ? 'not-allowed' : 'pointer',
            opacity: isScanning || scan.isPending ? 0.6 : 1,
          }}
        >
          {isScanning || scan.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <ScanLine size={14} />
          )}
          {isScanning ? t('connections.standalone.scanning') : t('connections.standalone.scan_btn')}
        </button>
      </div>

      <p className="text-sm" style={{ color: 'var(--muted-foreground)' }}>
        {isAutoActivated
          ? t('connections.standalone.desc_auto')
          : isActive
          ? t('connections.standalone.desc_active')
          : t('connections.standalone.desc_inactive')}
      </p>
    </div>
  )
}

// ─── Exported Sections (used by ConnectionsSettings orchestrator) ─────────────

export function SonarrSection() {
  const { t } = useTranslation('settings')
  return (
    <SettingsSection
      data-testid="sonarr-section"
      title={t('connections_media_servers.sonarr')}
      description={t('connections.sonarr.section_desc')}
      icon={<Link size={16} style={{ color: 'var(--accent)' }} />}
    >
      <div className="py-3">
        <SonarrMultiInstanceSection />
      </div>
    </SettingsSection>
  )
}

export function RadarrSection() {
  const { t } = useTranslation('settings')
  return (
    <SettingsSection
      data-testid="radarr-section"
      title={t('connections_media_servers.radarr')}
      description={t('connections.radarr.section_desc')}
      icon={<PlugZap size={16} style={{ color: 'var(--accent)' }} />}
    >
      <div className="py-3">
        <RadarrMultiInstanceSection />
      </div>
    </SettingsSection>
  )
}

export function MediaServersSection() {
  const { t } = useTranslation('settings')
  return (
    <SettingsSection
      data-testid="media-servers-section"
      title={t('connections_media_servers.title')}
      description={t('connections.media_servers.section_desc')}
      icon={<Server size={16} style={{ color: 'var(--accent)' }} />}
    >
      <div className="py-3">
        <Suspense fallback={<TabSkeleton />}>
          <MediaServersTab />
        </Suspense>
      </div>
    </SettingsSection>
  )
}

export function StandaloneModeSection() {
  const { t } = useTranslation('settings')
  return (
    <SettingsSection
      title={t('connections.standalone.section_title')}
      description={t('connections.standalone.section_desc')}
      icon={<ScanLine size={16} style={{ color: 'var(--accent)' }} />}
      advanced={
        <Suspense fallback={<TabSkeleton />}>
          <StandaloneSettingsTab />
        </Suspense>
      }
    >
      <div className="py-3">
        <StandaloneSection />
      </div>
    </SettingsSection>
  )
}
