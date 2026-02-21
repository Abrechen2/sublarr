import { useState, useEffect } from 'react'
import {
  useBackends, useTestBackend, useBackendConfig, useSaveBackendConfig, useBackendStats,
  usePromptPresets, useCreatePromptPreset, useUpdatePromptPreset, useDeletePromptPreset,
  useGlobalGlossaryEntries, useCreateGlossaryEntry, useUpdateGlossaryEntry, useDeleteGlossaryEntry,
} from '@/hooks/useApi'
import { Save, Loader2, TestTube, ChevronUp, ChevronDown, Trash2, Plus, Edit2, X, Check, Activity, Eye, EyeOff, BookOpen, Search } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { SettingRow } from '@/components/shared/SettingRow'
import type { TranslationBackendInfo, BackendStats, BackendHealthResult } from '@/lib/types'

// ─── Translation Backend Card ────────────────────────────────────────────────

function BackendCard({
  backend,
  stats,
  onTest,
  testResult,
}: {
  backend: TranslationBackendInfo
  stats?: BackendStats
  onTest: () => void
  testResult?: BackendHealthResult | 'testing'
}) {
  const [expanded, setExpanded] = useState(false)
  const [formValues, setFormValues] = useState<Record<string, string>>({})
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})
  const { data: configData } = useBackendConfig(expanded ? backend.name : '')
  const saveConfigMut = useSaveBackendConfig()

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
        onSuccess: () => toast('Backend config saved'),
        onError: () => toast('Failed to save backend config', 'error'),
      }
    )
  }

  const successRate = stats && stats.total_requests > 0
    ? Math.round((stats.successful_translations / stats.total_requests) * 100)
    : null

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
          {backend.supports_glossary && (
            <span
              className="px-1.5 py-0.5 rounded text-[10px] font-medium"
              style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
            >
              Glossary
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {successRate !== null && (
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {successRate}% success
            </span>
          )}
          {expanded ? <ChevronUp size={16} style={{ color: 'var(--text-muted)' }} /> : <ChevronDown size={16} style={{ color: 'var(--text-muted)' }} />}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4" style={{ borderTop: '1px solid var(--border)' }}>
          {/* Stats row */}
          {stats && stats.total_requests > 0 && (
            <div className="pt-3 space-y-2">
              <div className="flex items-center gap-2">
                <Activity size={12} style={{ color: 'var(--text-muted)' }} />
                <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  Statistics
                </span>
              </div>
              {/* Success rate bar */}
              <div className="flex items-center gap-2">
                <span className="text-xs w-8" style={{ color: 'var(--text-muted)' }}>
                  {successRate}%
                </span>
                <div className="flex-1 h-1.5 rounded-full" style={{ backgroundColor: 'var(--bg-primary)' }}>
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${successRate}%`,
                      backgroundColor: (successRate ?? 0) > 80
                        ? 'rgb(16 185 129)'
                        : (successRate ?? 0) > 50
                          ? 'rgb(245 158 11)'
                          : 'rgb(239 68 68)',
                    }}
                  />
                </div>
              </div>
              <div className="flex items-center gap-3 flex-wrap text-xs" style={{ color: 'var(--text-muted)' }}>
                <span>{stats.successful_translations}/{stats.total_requests} requests</span>
                {stats.avg_response_time_ms > 0 && (
                  <span>Avg: {Math.round(stats.avg_response_time_ms)}ms</span>
                )}
                {stats.last_response_time_ms > 0 && (
                  <span>Last: {Math.round(stats.last_response_time_ms)}ms</span>
                )}
                {stats.total_characters > 0 && (
                  <span>{stats.total_characters.toLocaleString()} chars</span>
                )}
                {stats.consecutive_failures > 0 && (
                  <span style={{ color: 'rgb(245 158 11)' }}>
                    {stats.consecutive_failures} consecutive failures
                  </span>
                )}
              </div>
              {stats.last_error && (
                <div className="text-xs truncate" style={{ color: 'var(--error)' }} title={stats.last_error}>
                  Last error: {stats.last_error}
                </div>
              )}
            </div>
          )}

          {/* Config form */}
          {backend.config_fields.length > 0 && (
            <div
              className="space-y-3 pt-3"
              style={{ borderTop: stats && stats.total_requests > 0 ? '1px solid var(--border)' : undefined }}
            >
              {backend.config_fields.map((field) => (
                <SettingRow
                  key={field.key}
                  label={`${field.label}${field.required ? ' *' : ''}`}
                  helpText={field.help}
                >
                  <div className="flex items-center gap-1.5 w-full">
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
                </SettingRow>
              ))}
            </div>
          )}

          {backend.config_fields.length === 0 && (
            <div className="pt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
              No configuration required for this backend.
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

          {/* Backend info */}
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            Max batch size: {backend.max_batch_size} lines
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Translation Backends Tab ────────────────────────────────────────────────

export function TranslationBackendsTab() {
  const { data: backendsData, isLoading: backendsLoading } = useBackends()
  const { data: statsData } = useBackendStats()
  const testBackendMut = useTestBackend()
  const [testResults, setTestResults] = useState<Record<string, BackendHealthResult | 'testing'>>({})

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

  if (backendsLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {backends.length} translation backends available &mdash; expand to configure and test
        </span>
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
    </div>
  )
}

// ─── Prompt Presets Tab ────────────────────────────────────────────────────────

export function PromptPresetsTab() {
  const { data, isLoading } = usePromptPresets()
  const createPreset = useCreatePromptPreset()
  const updatePreset = useUpdatePromptPreset()
  const deletePreset = useDeletePromptPreset()
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [formData, setFormData] = useState({ name: '', prompt_template: '', is_default: false })

  const presets = data?.presets || []

  const resetForm = () => {
    setShowAdd(false)
    setEditingId(null)
    setFormData({ name: '', prompt_template: '', is_default: false })
  }

  const startEdit = (preset: { id: number; name: string; prompt_template: string; is_default: number }) => {
    setEditingId(preset.id)
    setFormData({
      name: preset.name,
      prompt_template: preset.prompt_template,
      is_default: preset.is_default === 1,
    })
    setShowAdd(false)
  }

  const handleSave = () => {
    if (!formData.name.trim() || !formData.prompt_template.trim()) {
      toast('Name and prompt template are required', 'error')
      return
    }

    if (editingId) {
      updatePreset.mutate(
        { presetId: editingId, ...formData },
        {
          onSuccess: () => {
            toast('Preset updated')
            resetForm()
          },
          onError: () => toast('Failed to update preset', 'error'),
        }
      )
    } else {
      createPreset.mutate(formData, {
        onSuccess: () => {
          toast('Preset created')
          resetForm()
        },
        onError: () => toast('Failed to create preset', 'error'),
      })
    }
  }

  const handleDelete = (id: number) => {
    if (!confirm('Delete this preset? You cannot delete the last preset.')) return
    deletePreset.mutate(id, {
      onSuccess: () => toast('Preset deleted'),
      onError: () => toast('Failed to delete preset', 'error'),
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
          Prompt Presets
        </h2>
        <button
          onClick={() => {
            resetForm()
            setShowAdd(true)
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          <Plus size={12} />
          Add Preset
        </button>
      </div>

      {showAdd && (
        <div
          className="rounded-lg p-4 space-y-3"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {editingId ? 'Edit Preset' : 'New Preset'}
          </div>
          <div className="space-y-2">
            <input
              type="text"
              placeholder="Preset name"
              value={formData.name}
              onChange={(e) => setFormData((f) => ({ ...f, name: e.target.value }))}
              className="w-full px-3 py-2 rounded-md text-sm"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
            <textarea
              placeholder="Prompt template..."
              value={formData.prompt_template}
              onChange={(e) => setFormData((f) => ({ ...f, prompt_template: e.target.value }))}
              rows={8}
              className="w-full px-3 py-2 rounded-md text-sm font-mono"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
              }}
            />
            <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
              <input
                type="checkbox"
                checked={formData.is_default}
                onChange={(e) => setFormData((f) => ({ ...f, is_default: e.target.checked }))}
              />
              Set as default
            </label>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={createPreset.isPending || updatePreset.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {(createPreset.isPending || updatePreset.isPending) ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Check size={12} />
              )}
              Save
            </button>
            <button onClick={resetForm} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
              <X size={12} /> Cancel
            </button>
          </div>
        </div>
      )}

      {presets.map((p) => (
        <div
          key={p.id}
          className="rounded-lg p-4 space-y-2"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{p.name}</span>
              {p.is_default === 1 && (
                <span
                  className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                  style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
                >
                  Default
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => startEdit(p)}
                className="p-1.5 rounded transition-all duration-150"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
                title="Edit preset"
              >
                <Edit2 size={12} />
              </button>
              {presets.length > 1 && (
                <button
                  onClick={() => handleDelete(p.id)}
                  disabled={deletePreset.isPending}
                  className="p-1.5 rounded transition-all duration-150"
                  style={{ border: '1px solid var(--border)', color: 'var(--error)', backgroundColor: 'var(--bg-primary)' }}
                  title="Delete preset"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          </div>
          {editingId === p.id ? (
            <div className="space-y-2">
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData((f) => ({ ...f, name: e.target.value }))}
                className="w-full px-3 py-2 rounded-md text-sm"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                }}
              />
              <textarea
                value={formData.prompt_template}
                onChange={(e) => setFormData((f) => ({ ...f, prompt_template: e.target.value }))}
                rows={8}
                className="w-full px-3 py-2 rounded-md text-sm font-mono"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                }}
              />
              <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                <input
                  type="checkbox"
                  checked={formData.is_default}
                  onChange={(e) => setFormData((f) => ({ ...f, is_default: e.target.checked }))}
                />
                Set as default
              </label>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSave}
                  disabled={updatePreset.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
                  style={{ backgroundColor: 'var(--accent)' }}
                >
                  {updatePreset.isPending ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Check size={12} />
                  )}
                  Save
                </button>
                <button onClick={resetForm} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
                  <X size={12} /> Cancel
                </button>
              </div>
            </div>
          ) : (
            <div
              className="rounded px-3 py-2 text-xs font-mono max-h-32 overflow-auto"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
                whiteSpace: 'pre-wrap',
              }}
            >
              {p.prompt_template}
            </div>
          )}
        </div>
      ))}

      {presets.length === 0 && !showAdd && (
        <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
          No prompt presets configured. A default preset will be created automatically.
        </div>
      )}
    </div>
  )
}

// ─── Global Glossary Panel ──────────────────────────────────────────────────

export function GlobalGlossaryPanel() {
  const { data, isLoading } = useGlobalGlossaryEntries()
  const createEntry = useCreateGlossaryEntry()
  const updateEntry = useUpdateGlossaryEntry()
  const deleteEntry = useDeleteGlossaryEntry()
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [formData, setFormData] = useState({ source_term: '', target_term: '', notes: '' })

  const entries = data?.entries || []
  const filteredEntries = searchQuery
    ? entries.filter((e) =>
        e.source_term.toLowerCase().includes(searchQuery.toLowerCase()) ||
        e.target_term.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : entries

  const resetForm = () => {
    setShowAdd(false)
    setEditingId(null)
    setFormData({ source_term: '', target_term: '', notes: '' })
  }

  const startEdit = (entry: { id: number; source_term: string; target_term: string; notes: string }) => {
    setEditingId(entry.id)
    setFormData({
      source_term: entry.source_term,
      target_term: entry.target_term,
      notes: entry.notes || '',
    })
    setShowAdd(false)
  }

  const handleSave = () => {
    if (!formData.source_term.trim() || !formData.target_term.trim()) {
      toast('Source and target terms are required', 'error')
      return
    }

    if (editingId) {
      updateEntry.mutate(
        { entryId: editingId, series_id: null, ...formData },
        {
          onSuccess: () => {
            toast('Glossary entry updated')
            resetForm()
          },
          onError: () => toast('Failed to update entry', 'error'),
        }
      )
    } else {
      createEntry.mutate(
        { series_id: null, ...formData },
        {
          onSuccess: () => {
            toast('Glossary entry created')
            resetForm()
          },
          onError: () => toast('Failed to create entry', 'error'),
        }
      )
    }
  }

  const handleDelete = (id: number) => {
    if (!confirm('Delete this glossary entry?')) return
    deleteEntry.mutate(
      { entryId: id, seriesId: null },
      {
        onSuccess: () => toast('Entry deleted'),
        onError: () => toast('Failed to delete entry', 'error'),
      }
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen size={16} style={{ color: 'var(--accent)' }} />
          <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
            Global Glossary
          </h2>
          <span
            className="px-1.5 py-0.5 rounded text-[10px] font-medium"
            style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
          >
            {entries.length}
          </span>
        </div>
        <button
          onClick={() => {
            resetForm()
            setShowAdd(true)
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          <Plus size={12} />
          Add Entry
        </button>
      </div>

      {/* Search */}
      {entries.length > 0 && (
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Search glossary entries..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 rounded-md text-sm"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          />
        </div>
      )}

      {/* Add/Edit Form */}
      {(showAdd || editingId !== null) && (
        <div
          className="rounded-lg p-4 space-y-3"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {editingId ? 'Edit Entry' : 'New Global Entry'}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>
                Source Term
              </label>
              <input
                type="text"
                placeholder="e.g. Titan"
                value={formData.source_term}
                onChange={(e) => setFormData((f) => ({ ...f, source_term: e.target.value }))}
                className="w-full px-3 py-2 rounded-md text-sm"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>
                Target Term
              </label>
              <input
                type="text"
                placeholder="e.g. Titan"
                value={formData.target_term}
                onChange={(e) => setFormData((f) => ({ ...f, target_term: e.target.value }))}
                className="w-full px-3 py-2 rounded-md text-sm"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>
              Notes (optional)
            </label>
            <input
              type="text"
              placeholder="Context or usage notes"
              value={formData.notes}
              onChange={(e) => setFormData((f) => ({ ...f, notes: e.target.value }))}
              className="w-full px-3 py-2 rounded-md text-sm"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={createEntry.isPending || updateEntry.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {(createEntry.isPending || updateEntry.isPending) ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Check size={12} />
              )}
              Save
            </button>
            <button onClick={resetForm} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
              <X size={12} /> Cancel
            </button>
          </div>
        </div>
      )}

      {/* Entries List */}
      {filteredEntries.length === 0 ? (
        <div
          className="rounded-lg p-6 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <BookOpen size={24} className="mx-auto mb-2" style={{ color: 'var(--text-muted)', opacity: 0.5 }} />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            {searchQuery
              ? 'No entries match your search.'
              : 'No global glossary entries. Add terms that should be consistently translated across all series.'}
          </p>
        </div>
      ) : (
        <div className="rounded-md overflow-hidden" style={{ border: '1px solid var(--border)' }}>
          <table className="w-full">
            <thead>
              <tr style={{ backgroundColor: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-2" style={{ color: 'var(--text-muted)' }}>Source</th>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-2" style={{ color: 'var(--text-muted)' }}>Target</th>
                <th className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-2" style={{ color: 'var(--text-muted)' }}>Notes</th>
                <th className="text-right text-[10px] font-semibold uppercase tracking-wider px-3 py-2" style={{ color: 'var(--text-muted)' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredEntries.map((entry, i) => (
                <tr
                  key={entry.id}
                  style={{ borderBottom: i < filteredEntries.length - 1 ? '1px solid var(--border)' : undefined }}
                >
                  <td className="px-3 py-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {entry.source_term}
                  </td>
                  <td className="px-3 py-2 text-sm font-medium" style={{ color: 'var(--accent)' }}>
                    {entry.target_term}
                  </td>
                  <td className="px-3 py-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                    {entry.notes || '-'}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1 justify-end">
                      <button
                        onClick={() => startEdit(entry)}
                        className="p-1.5 rounded transition-all duration-150"
                        style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
                        title="Edit entry"
                      >
                        <Edit2 size={12} />
                      </button>
                      <button
                        onClick={() => handleDelete(entry.id)}
                        disabled={deleteEntry.isPending}
                        className="p-1.5 rounded transition-all duration-150"
                        style={{ border: '1px solid var(--border)', color: 'var(--error)', backgroundColor: 'var(--bg-primary)' }}
                        title="Delete entry"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
