import { useState, useEffect, useRef, lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useConfig, useUpdateConfig,
  useRetranslateStatus, useRetranslateBatch,
  useExportConfig, useImportConfig,
} from '@/hooks/useApi'
import {
  Save, Loader2, TestTube, Trash2, Plus, RefreshCw, Upload, FileDown, X, Check,
  Settings2, Download, Server, Languages, Zap, Globe, Cog,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { getHealth } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import { Toggle } from '@/components/shared/Toggle'
import { SettingRow } from '@/components/shared/SettingRow'
import { HELP_TEXT } from './settingsHelpText'

// Tab sub-components — lazy loaded so each tab's code is only fetched on first open
const ProvidersTab = lazy(() => import('./ProvidersTab').then(m => ({ default: m.ProvidersTab })))
const TranslationBackendsTab = lazy(() => import('./TranslationTab').then(m => ({ default: m.TranslationBackendsTab })))
const PromptPresetsTab = lazy(() => import('./TranslationTab').then(m => ({ default: m.PromptPresetsTab })))
const GlobalGlossaryPanel = lazy(() => import('./TranslationTab').then(m => ({ default: m.GlobalGlossaryPanel })))
const ContextWindowSizeRow = lazy(() => import('./TranslationTab').then(m => ({ default: m.ContextWindowSizeRow })))
const DefaultSyncEngineRow = lazy(() => import('./TranslationTab').then(m => ({ default: m.DefaultSyncEngineRow })))
const AutoSyncSection = lazy(() => import('./TranslationTab').then(m => ({ default: m.AutoSyncSection })))
const TranslationMemorySection = lazy(() => import('./TranslationTab').then(m => ({ default: m.TranslationMemorySection })))
const TranslationQualitySection = lazy(() => import('./TranslationTab').then(m => ({ default: m.TranslationQualitySection })))
const WhisperTab = lazy(() => import('./WhisperTab').then(m => ({ default: m.WhisperTab })))
const MediaServersTab = lazy(() => import('./MediaServersTab').then(m => ({ default: m.MediaServersTab })))
const EventsHooksTab = lazy(() => import('./EventsTab').then(m => ({ default: m.EventsHooksTab })))
const ScoringTab = lazy(() => import('./EventsTab').then(m => ({ default: m.ScoringTab })))
const LanguageProfilesTab = lazy(() => import('./AdvancedTab').then(m => ({ default: m.LanguageProfilesTab })))
const LibrarySourcesTab = lazy(() => import('./AdvancedTab').then(m => ({ default: m.LibrarySourcesTab })))
const BackupTab = lazy(() => import('./AdvancedTab').then(m => ({ default: m.BackupTab })))
const SubtitleToolsTab = lazy(() => import('./AdvancedTab').then(m => ({ default: m.SubtitleToolsTab })))
const ApiKeysTab = lazy(() => import('./ApiKeysTab').then(m => ({ default: m.ApiKeysTab })))
const NotificationTemplatesTab = lazy(() => import('./NotificationTemplatesTab').then(m => ({ default: m.NotificationTemplatesTab })))
const CleanupTab = lazy(() => import('./CleanupTab').then(m => ({ default: m.CleanupTab })))
const IntegrationsTab = lazy(() => import('./IntegrationsTab').then(m => ({ default: m.IntegrationsTab })))
const MigrationTab = lazy(() => import('./MigrationTab').then(m => ({ default: m.MigrationTab })))

function TabSkeleton() {
  return (
    <div className="rounded-lg p-5 animate-pulse" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
      <div className="space-y-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-10 rounded" style={{ backgroundColor: 'var(--bg-primary)' }} />
        ))}
      </div>
    </div>
  )
}

// ─── Navigation Groups ────────────────────────────────────────────────────────

interface NavGroup {
  title: string
  icon: LucideIcon
  items: string[]
}

const NAV_GROUPS: NavGroup[] = [
  { title: 'General',     icon: Settings2,  items: ['General', 'API Keys'] },
  { title: 'Download',    icon: Download,   items: ['Sonarr', 'Radarr', 'Library Sources'] },
  { title: 'Servers',     icon: Server,     items: ['Media Servers'] },
  { title: 'Translation', icon: Languages,  items: ['Translation', 'Translation Backends', 'Prompt Presets', 'Languages'] },
  { title: 'Automation',  icon: Zap,        items: ['Automation', 'Wanted', 'Whisper'] },
  { title: 'Providers',   icon: Globe,      items: ['Providers', 'Scoring'] },
  { title: 'System',      icon: Cog,        items: ['Events & Hooks', 'Backup', 'Subtitle Tools', 'Cleanup', 'Integrations', 'Notification Templates', 'Migration'] },
]

// Flat list derived from groups (preserves ordering for legacy code)
const TABS = NAV_GROUPS.flatMap((g) => g.items)

export interface FieldConfig {
  key: string
  label: string
  type: 'text' | 'number' | 'password' | 'toggle'
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
  // Translation
  { key: 'source_language', label: 'Source Language Code', type: 'text', placeholder: 'en', tab: 'Translation' },
  { key: 'target_language', label: 'Target Language Code', type: 'text', placeholder: 'de', tab: 'Translation' },
  { key: 'source_language_name', label: 'Source Language Name', type: 'text', placeholder: 'English', tab: 'Translation' },
  { key: 'target_language_name', label: 'Target Language Name', type: 'text', placeholder: 'German', tab: 'Translation' },
  { key: 'hi_removal_enabled', label: 'Remove Hearing Impaired Tags', type: 'toggle', tab: 'Translation' },
  // Automation — Upgrade
  { key: 'upgrade_enabled', label: 'Upgrade Enabled', type: 'toggle', tab: 'Automation' },
  { key: 'upgrade_prefer_ass', label: 'Prefer ASS over SRT', type: 'toggle', tab: 'Automation' },
  { key: 'upgrade_min_score_delta', label: 'Min Score Delta', type: 'number', placeholder: '50', tab: 'Automation' },
  { key: 'upgrade_window_days', label: 'Upgrade Window (days)', type: 'number', placeholder: '7', tab: 'Automation' },
  // Automation — Webhook
  { key: 'webhook_delay_minutes', label: 'Webhook Delay (minutes)', type: 'number', placeholder: '5', tab: 'Automation' },
  { key: 'webhook_auto_scan', label: 'Auto-Scan after Download', type: 'toggle', tab: 'Automation' },
  { key: 'webhook_auto_search', label: 'Auto-Search Providers', type: 'toggle', tab: 'Automation' },
  { key: 'webhook_auto_translate', label: 'Auto-Translate Found Subs', type: 'toggle', tab: 'Automation' },
  // Automation — Search Scheduler
  { key: 'wanted_search_interval_hours', label: 'Search Interval (hours, 0=disabled)', type: 'number', placeholder: '24', tab: 'Automation' },
  { key: 'wanted_search_on_startup', label: 'Search on Startup', type: 'toggle', tab: 'Automation' },
  { key: 'wanted_search_max_items_per_run', label: 'Max Items per Search Run', type: 'number', placeholder: '50', tab: 'Automation' },
  // Wanted
  { key: 'wanted_scan_interval_hours', label: 'Scan Interval (hours, 0=disabled)', type: 'number', placeholder: '6', tab: 'Wanted' },
  { key: 'wanted_anime_only', label: 'Anime Only (Sonarr)', type: 'toggle', tab: 'Wanted' },
  { key: 'wanted_anime_movies_only', label: 'Anime Movies Only (Radarr)', type: 'toggle', tab: 'Wanted' },
  { key: 'wanted_scan_on_startup', label: 'Scan on Startup', type: 'toggle', tab: 'Wanted' },
  { key: 'wanted_max_search_attempts', label: 'Max Search Attempts', type: 'number', placeholder: '3', tab: 'Wanted' },
  // Sonarr
  { key: 'sonarr_url', label: 'Sonarr URL', type: 'text', placeholder: 'http://localhost:8989', tab: 'Sonarr' },
  { key: 'sonarr_api_key', label: 'Sonarr API Key', type: 'password', tab: 'Sonarr' },
  // Radarr
  { key: 'radarr_url', label: 'Radarr URL', type: 'text', placeholder: 'http://localhost:7878', tab: 'Radarr' },
  { key: 'radarr_api_key', label: 'Radarr API Key', type: 'password', tab: 'Radarr' },
  // Library Sources (Standalone Mode)
  { key: 'standalone_enabled', label: 'Enable Standalone Mode', type: 'toggle', tab: 'Library Sources' },
  { key: 'tmdb_api_key', label: 'TMDB API Key (Bearer Token)', type: 'password', tab: 'Library Sources' },
  { key: 'tvdb_api_key', label: 'TVDB API Key (Optional)', type: 'password', tab: 'Library Sources' },
  { key: 'tvdb_pin', label: 'TVDB PIN (Optional)', type: 'password', tab: 'Library Sources' },
  { key: 'standalone_scan_interval_hours', label: 'Scan Interval (hours, 0=disabled)', type: 'number', placeholder: '6', tab: 'Library Sources' },
  { key: 'standalone_debounce_seconds', label: 'File Detection Debounce (seconds)', type: 'number', placeholder: '10', tab: 'Library Sources' },
]

// ─── Path Mapping Editor ────────────────────────────────────────────────────

function PathMappingEditor({
  value,
  onChange,
}: {
  value: string
  onChange: (val: string) => void
}) {
  const [testPath, setTestPath] = useState('')
  const [testResult, setTestResult] = useState<{ mapped_path: string; exists: boolean } | null>(null)
  const [isTesting, setIsTesting] = useState(false)

  const handleTestPath = async () => {
    if (!testPath.trim()) return
    setIsTesting(true)
    try {
      const { default: api } = await import('@/api/client')
      const { data } = await api.post('/settings/path-mapping/test', { remote_path: testPath })
      setTestResult(data)
    } catch (error: unknown) {
      const msg = (error as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Path mapping test failed'
      toast(msg, 'error')
      setTestResult(null)
    } finally {
      setIsTesting(false)
    }
  }
  const parseRows = (val: string): { remote: string; local: string }[] => {
    if (!val || !val.trim()) return []
    return val.split(';').filter(Boolean).map((pair) => {
      const eqIdx = pair.indexOf('=')
      if (eqIdx === -1) return { remote: pair, local: '' }
      return { remote: pair.slice(0, eqIdx), local: pair.slice(eqIdx + 1) }
    })
  }

  const rows = parseRows(value)

  const serialize = (r: { remote: string; local: string }[]) =>
    r.filter((x) => x.remote || x.local).map((x) => `${x.remote}=${x.local}`).join(';')

  const updateRow = (index: number, field: 'remote' | 'local', newVal: string) => {
    const updated = [...rows]
    updated[index] = { ...updated[index], [field]: newVal }
    onChange(serialize(updated))
  }

  const removeRow = (index: number) => {
    onChange(serialize(rows.filter((_, i) => i !== index)))
  }

  const addRow = () => {
    onChange(value ? value + ';=' : '=')
  }

  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
        Path Mapping (Remote &rarr; Local)
      </label>
      <div className="space-y-2">
        {rows.length > 0 && (
          <div
            className="grid gap-2 text-xs font-medium"
            style={{ gridTemplateColumns: '1fr 1fr 2rem', color: 'var(--text-muted)' }}
          >
            <span>Remote Path</span>
            <span>Local Path</span>
            <span />
          </div>
        )}
        {rows.map((row, i) => (
          <div
            key={i}
            className="grid gap-2 items-center"
            style={{ gridTemplateColumns: '1fr 1fr 2rem' }}
          >
            <input
              type="text"
              value={row.remote}
              onChange={(e) => updateRow(i, 'remote', e.target.value)}
              placeholder="/data/media"
              className="px-3 py-2 rounded-md text-sm focus:outline-none"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
              }}
            />
            <input
              type="text"
              value={row.local}
              onChange={(e) => updateRow(i, 'local', e.target.value)}
              placeholder="Z:\Media"
              className="px-3 py-2 rounded-md text-sm focus:outline-none"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
              }}
            />
            <button
              onClick={() => removeRow(i)}
              className="p-1.5 rounded transition-all duration-150"
              style={{ color: 'var(--text-muted)' }}
              title="Remove mapping"
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <button
          onClick={addRow}
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
          <Plus size={12} />
          Add Mapping
        </button>
      </div>
      {/* Test Path Mapping */}
      <div className="pt-3 space-y-2" style={{ borderTop: '1px solid var(--border)' }}>
        <label className="block text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          Test Path Mapping
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={testPath}
            onChange={(e) => setTestPath(e.target.value)}
            placeholder="/data/media/anime/Series.mkv"
            className="flex-1 px-3 py-2 rounded-md text-sm focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
              fontSize: '13px',
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleTestPath()
            }}
          />
          <button
            onClick={handleTestPath}
            disabled={isTesting || !testPath.trim()}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
            }}
            onMouseEnter={(e) => {
              if (!e.currentTarget.disabled) {
                e.currentTarget.style.borderColor = 'var(--accent-dim)'
                e.currentTarget.style.color = 'var(--accent)'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.color = 'var(--text-secondary)'
            }}
          >
            {isTesting ? <Loader2 size={14} className="animate-spin" /> : <TestTube size={14} />}
            Test
          </button>
        </div>
        {testResult && (
          <div className="text-xs space-y-1" style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Mapped to:</span>{' '}
              <span style={{ color: 'var(--accent)' }}>{testResult.mapped_path}</span>
            </div>
            <div>
              <span style={{ color: testResult.exists ? 'var(--success)' : 'var(--error)' }}>
                {testResult.exists ? '\u2713 File exists' : '\u2717 File not found'}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Instance Editor Component ──────────────────────────────────────────────

interface InstanceEntry {
  name: string
  url: string
  api_key: string
  path_mapping?: string
}

function InstanceEditor({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (val: string) => void
}) {
  const [instances, setInstances] = useState<InstanceEntry[]>(() => {
    try {
      const parsed = JSON.parse(value || '[]')
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  })

  const sync = (updated: InstanceEntry[]) => {
    setInstances(updated)
    onChange(updated.length > 0 ? JSON.stringify(updated) : '')
  }

  const addInstance = () => {
    sync([...instances, { name: '', url: '', api_key: '', path_mapping: '' }])
  }

  const removeInstance = (idx: number) => {
    sync(instances.filter((_, i) => i !== idx))
  }

  const updateField = (idx: number, field: keyof InstanceEntry, val: string) => {
    const updated = [...instances]
    updated[idx] = { ...updated[idx], [field]: val }
    sync(updated)
  }

  const inputStyle = {
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
  }

  return (
    <div className="pt-3 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {label} Instances
        </h3>
        <button
          onClick={addInstance}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all duration-150"
          style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
        >
          <Plus size={12} />
          Add Instance
        </button>
      </div>
      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
        Configure multiple {label} instances. If empty, the legacy URL/Key above is used.
      </p>
      {instances.map((inst, idx) => (
        <div
          key={idx}
          className="rounded-lg p-3 space-y-2"
          style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Instance {idx + 1}
            </span>
            <button
              onClick={() => removeInstance(idx)}
              className="p-1 rounded transition-colors"
              style={{ color: 'var(--text-muted)' }}
            >
              <Trash2 size={12} />
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input
              type="text"
              placeholder="Name (e.g. Main)"
              value={inst.name}
              onChange={(e) => updateField(idx, 'name', e.target.value)}
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={inputStyle}
            />
            <input
              type="text"
              placeholder="URL (e.g. http://localhost:8989)"
              value={inst.url}
              onChange={(e) => updateField(idx, 'url', e.target.value)}
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={inputStyle}
            />
            <input
              type="password"
              placeholder="API Key"
              value={inst.api_key}
              onChange={(e) => updateField(idx, 'api_key', e.target.value)}
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={inputStyle}
            />
            <input
              type="text"
              placeholder="Path Mapping (optional)"
              value={inst.path_mapping || ''}
              onChange={(e) => updateField(idx, 'path_mapping', e.target.value)}
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={inputStyle}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Settings Page ──────────────────────────────────────────────────────────

// Map internal tab IDs to i18n translation keys
const TAB_KEYS: Record<string, string> = {
  'General': 'tabs.general',
  'API Keys': 'tabs.api_keys',
  'Translation': 'tabs.translation',
  'Translation Backends': 'tabs.translation_backends',
  'Languages': 'tabs.languages',
  'Automation': 'tabs.automation',
  'Wanted': 'tabs.wanted',
  'Providers': 'tabs.providers',
  'Sonarr': 'tabs.sonarr',
  'Radarr': 'tabs.radarr',
  'Library Sources': 'tabs.library_sources',
  'Media Servers': 'tabs.media_servers',
  'Whisper': 'tabs.whisper',
  'Events & Hooks': 'tabs.events_hooks',
  'Scoring': 'tabs.scoring',
  'Backup': 'tabs.backup',
  'Subtitle Tools': 'tabs.subtitle_tools',
  'Cleanup': 'tabs.cleanup',
  'Integrations': 'tabs.integrations',
  'Notification Templates': 'tabs.notification_templates',
  'Prompt Presets': 'tabs.prompt_presets',
}

export function SettingsPage() {
  const { t } = useTranslation('settings')
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
      doSave(changed)
    }
  }

  const doSave = (changed: Record<string, unknown>) => {
    updateConfig.mutate(changed, {
      onSuccess: () => {
        toast('Settings saved successfully')
      },
      onError: () => {
        toast('Failed to save settings', 'error')
      },
    })
  }

  const handleTestConnection = async (service: string) => {
    setTestResults((prev) => ({ ...prev, [service]: 'testing...' }))
    try {
      const health = await getHealth()
      const serviceKey = service.replace(' (Legacy)', '').toLowerCase()
      const status = health.services[serviceKey] || 'unknown'
      setTestResults((prev) => ({ ...prev, [service]: status }))
    } catch {
      setTestResults((prev) => ({ ...prev, [service]: 'error' }))
    }
  }

  const retranslateStatus = useRetranslateStatus()
  const retranslateBatch = useRetranslateBatch()
  const exportConfig = useExportConfig()
  const importConfig = useImportConfig()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importPreview, setImportPreview] = useState<Record<string, unknown> | null>(null)

  const handleExport = () => {
    exportConfig.mutate(undefined, {
      onSuccess: (data) => {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `sublarr-config-${new Date().toISOString().slice(0, 10)}.json`
        a.click()
        URL.revokeObjectURL(url)
        toast('Config exported')
      },
      onError: () => toast('Export failed', 'error'),
    })
  }

  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(ev.target?.result as string)
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          toast('Invalid config file: expected JSON object', 'error')
          return
        }
        setImportPreview(parsed)
      } catch {
        toast('Invalid JSON file', 'error')
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const handleImportConfirm = () => {
    if (!importPreview) return
    importConfig.mutate(importPreview, {
      onSuccess: (result) => {
        setImportPreview(null)
        toast(`Imported ${result.imported_keys.length} settings` +
          (result.skipped_secrets.length > 0 ? ` (${result.skipped_secrets.length} secrets skipped)` : ''))
      },
      onError: () => toast('Import failed', 'error'),
    })
  }

  const tabFields = FIELDS.filter((f) => f.tab === activeTab)
  const hasTestConnection = ['Sonarr', 'Radarr'].includes(activeTab)
  const isProvidersTab = activeTab === 'Providers'
  const isLanguagesTab = activeTab === 'Languages'
  const isTranslationTab = activeTab === 'Translation'
  const isPromptPresetsTab = activeTab === 'Prompt Presets'
  const isTranslationBackendsTab = activeTab === 'Translation Backends'
  const isMediaServersTab = activeTab === 'Media Servers'
  const isLibrarySourcesTab = activeTab === 'Library Sources'
  const isWhisperTab = activeTab === 'Whisper'
  const isEventsHooksTab = activeTab === 'Events & Hooks'
  const isScoringTab = activeTab === 'Scoring'
  const isBackupTab = activeTab === 'Backup'
  const isSubtitleToolsTab = activeTab === 'Subtitle Tools'
  const isCleanupTab = activeTab === 'Cleanup'
  const isIntegrationsTab = activeTab === 'Integrations'
  const isApiKeysTab = activeTab === 'API Keys'
  const isMigrationTab = activeTab === 'Migration'
  const isNotificationTemplatesTab = activeTab === 'Notification Templates'

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
        <h1>{t('title')}</h1>
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
              {t('actions.save')}
            </>
          )}
        </button>
      </div>

      <div className="flex flex-col md:flex-row gap-5">
        {/* Grouped Navigation Sidebar */}
        <nav className="w-full md:w-52 shrink-0 flex flex-row md:flex-col gap-0 overflow-x-auto md:overflow-x-visible">
          {NAV_GROUPS.map((group) => {
            const Icon = group.icon
            return (
              <div key={group.title} className="mb-1">
                {/* Group header — non-clickable label with icon */}
                <div
                  className="hidden md:flex items-center gap-2 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider select-none"
                  style={{ color: 'var(--text-muted)' }}
                >
                  <Icon size={12} />
                  {group.title}
                </div>
                {/* Tab items */}
                <div className="flex flex-row md:flex-col gap-0.5">
                  {group.items.map((tab) => {
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
                        <span className="md:pl-1">
                          {TAB_KEYS[tab] ? t(TAB_KEYS[tab]) : tab}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </nav>

        {/* Content */}
        <div className="flex-1">
          <Suspense fallback={<TabSkeleton />}>
          {isApiKeysTab ? (
            <ApiKeysTab />
          ) : isProvidersTab ? (
            <ProvidersTab
              values={values}
              onFieldChange={(key, value) => setValues((v) => ({ ...v, [key]: value }))}
              onSave={doSave}
            />
          ) : isLanguagesTab ? (
            <LanguageProfilesTab />
          ) : isPromptPresetsTab ? (
            <PromptPresetsTab />
          ) : isTranslationBackendsTab ? (
            <TranslationBackendsTab />
          ) : isMediaServersTab ? (
            <MediaServersTab />
          ) : isLibrarySourcesTab ? (
            <LibrarySourcesTab
              values={values}
              onFieldChange={(key, value) => setValues((v) => ({ ...v, [key]: value }))}
              fields={FIELDS.filter((f) => f.tab === 'Library Sources')}
            />
          ) : isWhisperTab ? (
            <WhisperTab />
          ) : isEventsHooksTab ? (
            <EventsHooksTab />
          ) : isScoringTab ? (
            <ScoringTab />
          ) : isBackupTab ? (
            <BackupTab />
          ) : isSubtitleToolsTab ? (
            <SubtitleToolsTab />
          ) : isCleanupTab ? (
            <CleanupTab />
          ) : isIntegrationsTab ? (
            <IntegrationsTab />
          ) : isMigrationTab ? (
            <MigrationTab />
          ) : isNotificationTemplatesTab ? (
            <NotificationTemplatesTab />
          ) : isTranslationTab ? (
            <div className="space-y-5">
              <div
                className="rounded-lg p-5 space-y-4"
                style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
              >
                {tabFields.map((field) => (
                  <SettingRow
                    key={field.key}
                    label={field.label}
                    helpText={HELP_TEXT[field.key]}
                  >
                    {field.type === 'toggle' ? (
                      <Toggle
                        checked={values[field.key] === 'true'}
                        onChange={(v) => setValues((prev) => ({ ...prev, [field.key]: String(v) }))}
                      />
                    ) : (
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
                    )}
                  </SettingRow>
                ))}
                <ContextWindowSizeRow />
                <DefaultSyncEngineRow />
                <AutoSyncSection />
              </div>
              <TranslationMemorySection />
              <TranslationQualitySection />
              <GlobalGlossaryPanel />
            </div>
          ) : (
            <div
              className="rounded-lg p-5 space-y-4"
              style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
            >
              {tabFields.map((field) => (
                <SettingRow
                  key={field.key}
                  label={field.label}
                  helpText={HELP_TEXT[field.key]}
                >
                  {field.type === 'toggle' ? (
                    <Toggle
                      checked={values[field.key] === 'true'}
                      onChange={(v) => setValues((prev) => ({ ...prev, [field.key]: String(v) }))}
                    />
                  ) : (
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
                  )}
                </SettingRow>
              ))}

              {/* Path Mapping Table (General tab only) */}
              {activeTab === 'General' && (
                <PathMappingEditor
                  value={values.path_mapping ?? ''}
                  onChange={(val) => setValues((v) => ({ ...v, path_mapping: val }))}
                />
              )}

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

              {activeTab === 'Sonarr' && (
                <InstanceEditor
                  label="Sonarr"
                  value={values.sonarr_instances_json ?? ''}
                  onChange={(val) => setValues((v) => ({ ...v, sonarr_instances_json: val }))}
                />
              )}

              {activeTab === 'Radarr' && (
                <InstanceEditor
                  label="Radarr"
                  value={values.radarr_instances_json ?? ''}
                  onChange={(val) => setValues((v) => ({ ...v, radarr_instances_json: val }))}
                />
              )}

              {isTranslationTab && retranslateStatus.data && (
                <div className="pt-3 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
                  <div>
                    <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
                      Re-Translation
                    </h3>
                    <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
                      <span>
                        Config hash: <code style={{ fontFamily: 'var(--font-mono)' }}>{retranslateStatus.data.current_hash}</code>
                      </span>
                      <span>
                        Model: <code style={{ fontFamily: 'var(--font-mono)' }}>{retranslateStatus.data.ollama_model}</code>
                      </span>
                    </div>
                  </div>
                  {retranslateStatus.data.outdated_count > 0 ? (
                    <div className="flex items-center gap-3">
                      <span className="text-sm" style={{ color: 'var(--warning)' }}>
                        {retranslateStatus.data.outdated_count} files translated with old config
                      </span>
                      <button
                        onClick={() => retranslateBatch.mutate(undefined, {
                          onSuccess: () => toast('Re-translation started'),
                          onError: () => toast('Failed to start re-translation', 'error'),
                        })}
                        disabled={retranslateBatch.isPending}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white hover:opacity-90"
                        style={{ backgroundColor: 'var(--warning)' }}
                      >
                        {retranslateBatch.isPending ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <RefreshCw size={12} />
                        )}
                        Re-translate All
                      </button>
                    </div>
                  ) : (
                    <span className="text-xs" style={{ color: 'var(--success)' }}>
                      All translations are up to date
                    </span>
                  )}
                </div>
              )}

              {/* Config Export/Import (General tab only) */}
              {activeTab === 'General' && (
                <div className="pt-3 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
                  <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                    Config Backup
                  </h3>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      onClick={handleExport}
                      disabled={exportConfig.isPending}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
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
                      {exportConfig.isPending ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <FileDown size={14} />
                      )}
                      Export Config
                    </button>
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
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
                      <Upload size={14} />
                      Import Config
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".json"
                      onChange={handleImportFile}
                      className="hidden"
                    />
                  </div>
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    API keys and secrets are excluded from export/import for security.
                  </div>

                  {/* Import Preview Modal */}
                  {importPreview && (
                    <div
                      className="rounded-lg p-4 space-y-3"
                      style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--accent-dim)' }}
                    >
                      <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                        Import Preview
                      </div>
                      <div
                        className="max-h-48 overflow-auto rounded px-3 py-2 text-xs"
                        style={{
                          backgroundColor: 'var(--bg-surface)',
                          border: '1px solid var(--border)',
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--text-secondary)',
                        }}
                      >
                        {Object.entries(importPreview).map(([key, val]) => (
                          <div key={key} className="py-0.5">
                            <span style={{ color: 'var(--accent)' }}>{key}</span>
                            <span style={{ color: 'var(--text-muted)' }}>{': '}</span>
                            <span>{typeof val === 'string' ? val : JSON.stringify(val)}</span>
                          </div>
                        ))}
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleImportConfirm}
                          disabled={importConfig.isPending}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
                          style={{ backgroundColor: 'var(--accent)' }}
                        >
                          {importConfig.isPending ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <Check size={12} />
                          )}
                          Confirm Import
                        </button>
                        <button
                          onClick={() => setImportPreview(null)}
                          className="flex items-center gap-1 px-3 py-1.5 rounded text-xs"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          <X size={12} />
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          </Suspense>
        </div>
      </div>
    </div>
  )
}

// Re-export TABS for backward compat (used by nothing currently, but safe to keep)
export { TABS }
