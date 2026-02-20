import { useState, useEffect } from 'react'
import {
  useMediaServerTypes, useMediaServerInstances, useSaveMediaServerInstances, useTestMediaServer,
} from '@/hooks/useApi'
import { Save, Loader2, TestTube, ChevronUp, ChevronDown, Trash2, Plus, Eye, EyeOff } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { Toggle } from '@/components/shared/Toggle'
import { SettingRow } from '@/components/shared/SettingRow'
import type { MediaServerType, MediaServerInstance, MediaServerTestResult } from '@/lib/types'

export function MediaServersTab() {
  const { data: typesData, isLoading: typesLoading } = useMediaServerTypes()
  const { data: instancesData, isLoading: instancesLoading } = useMediaServerInstances()
  const saveMut = useSaveMediaServerInstances()
  const testMut = useTestMediaServer()

  const [localInstances, setLocalInstances] = useState<MediaServerInstance[]>([])
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})
  const [testResults, setTestResults] = useState<Record<number, MediaServerTestResult | 'testing'>>({})
  const [showAddDropdown, setShowAddDropdown] = useState(false)

  const types = typesData ?? []

  // Sync from server data
  useEffect(() => {
    if (instancesData) {
      setLocalInstances(instancesData)
    }
  }, [instancesData])

  const saveInstances = (updated: MediaServerInstance[]) => {
    setLocalInstances(updated)
    saveMut.mutate(updated, {
      onSuccess: () => toast('Media servers saved'),
      onError: () => toast('Failed to save media servers', 'error'),
    })
  }

  const addInstance = (serverType: MediaServerType) => {
    const newInstance: MediaServerInstance = {
      type: serverType.name,
      name: `${serverType.display_name}`,
      enabled: true,
    }
    // Initialize empty config fields
    for (const field of serverType.config_fields) {
      newInstance[field.key] = field.default ?? ''
    }
    const updated = [...localInstances, newInstance]
    saveInstances(updated)
    setExpandedIdx(updated.length - 1)
    setShowAddDropdown(false)
  }

  const removeInstance = (idx: number) => {
    if (!confirm(`Remove "${localInstances[idx].name}"?`)) return
    const updated = localInstances.filter((_, i) => i !== idx)
    saveInstances(updated)
    if (expandedIdx === idx) setExpandedIdx(null)
    else if (expandedIdx !== null && expandedIdx > idx) setExpandedIdx(expandedIdx - 1)
  }

  const updateInstance = (idx: number, key: string, value: unknown) => {
    const updated = [...localInstances]
    updated[idx] = { ...updated[idx], [key]: value }
    setLocalInstances(updated)
  }

  const handleSaveInstance = (idx: number) => {
    saveInstances(localInstances)
  }

  const toggleEnabled = (idx: number) => {
    const updated = [...localInstances]
    updated[idx] = { ...updated[idx], enabled: !updated[idx].enabled }
    saveInstances(updated)
  }

  const handleTest = (idx: number) => {
    const inst = localInstances[idx]
    setTestResults((prev) => ({ ...prev, [idx]: 'testing' }))
    testMut.mutate(inst as Record<string, unknown>, {
      onSuccess: (result) => {
        setTestResults((prev) => ({ ...prev, [idx]: result }))
        if (result.healthy) {
          toast(`${inst.name}: connection successful`)
        } else {
          toast(`${inst.name}: ${result.message}`, 'error')
        }
      },
      onError: () => {
        setTestResults((prev) => ({ ...prev, [idx]: { healthy: false, message: 'Test request failed' } }))
        toast(`${inst.name}: test failed`, 'error')
      },
    })
  }

  const getTypeInfo = (typeName: string) => types.find((t) => t.name === typeName)

  if (typesLoading || instancesLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {localInstances.length > 0
            ? `${localInstances.length} media server${localInstances.length !== 1 ? 's' : ''} configured`
            : 'No media servers configured'}
        </span>
        <div className="relative">
          <button
            onClick={() => setShowAddDropdown(!showAddDropdown)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium text-white"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            <Plus size={12} />
            Add Server
          </button>
          {showAddDropdown && (
            <div
              className="absolute right-0 top-full mt-1 z-10 rounded-lg py-1 min-w-[180px] shadow-lg"
              style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
            >
              {types.map((t) => (
                <button
                  key={t.name}
                  onClick={() => addInstance(t)}
                  className="w-full text-left px-3 py-2 text-sm transition-colors"
                  style={{ color: 'var(--text-primary)' }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent'
                  }}
                >
                  {t.display_name}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Instance cards */}
      {localInstances.map((inst, idx) => {
        const typeInfo = getTypeInfo(inst.type)
        const isExpanded = expandedIdx === idx
        const testResult = testResults[idx]

        return (
          <div
            key={idx}
            className="rounded-lg overflow-hidden"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              opacity: inst.enabled ? 1 : 0.7,
            }}
          >
            {/* Collapsed header */}
            <button
              onClick={() => setExpandedIdx(isExpanded ? null : idx)}
              className="w-full flex items-center justify-between gap-3 p-4 text-left transition-colors"
              style={{ backgroundColor: isExpanded ? 'var(--bg-surface-hover)' : undefined }}
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {inst.name || 'Unnamed'}
                </span>
                <span
                  className="px-2 py-0.5 rounded-full text-[10px] font-medium"
                  style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
                >
                  {typeInfo?.display_name ?? inst.type}
                </span>
                <span
                  className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium"
                  style={{
                    backgroundColor: inst.enabled ? 'var(--success-bg)' : 'rgba(124,130,147,0.08)',
                    color: inst.enabled ? 'var(--success)' : 'var(--text-muted)',
                  }}
                >
                  <span
                    className="w-1.5 h-1.5 rounded-full shrink-0"
                    style={{ backgroundColor: inst.enabled ? 'var(--success)' : 'var(--text-muted)' }}
                  />
                  {inst.enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {isExpanded ? <ChevronUp size={16} style={{ color: 'var(--text-muted)' }} /> : <ChevronDown size={16} style={{ color: 'var(--text-muted)' }} />}
              </div>
            </button>

            {/* Expanded content */}
            {isExpanded && (
              <div className="px-4 pb-4 space-y-4" style={{ borderTop: '1px solid var(--border)' }}>
                {/* Name field */}
                <div className="pt-3">
                  <SettingRow label="Name">
                    <input
                      type="text"
                      value={String(inst.name ?? '')}
                      onChange={(e) => updateInstance(idx, 'name', e.target.value)}
                      placeholder="e.g. Living Room Plex"
                      className="w-full px-2.5 py-1.5 rounded text-xs transition-all duration-150 focus:outline-none"
                      style={{
                        backgroundColor: 'var(--bg-primary)',
                        border: '1px solid var(--border)',
                        color: 'var(--text-primary)',
                      }}
                    />
                  </SettingRow>
                </div>

                {/* Dynamic config fields */}
                {typeInfo?.config_fields.map((field) => (
                  <SettingRow
                    key={field.key}
                    label={`${field.label}${field.required ? ' *' : ''}`}
                    helpText={field.help}
                  >
                    <div className="flex items-center gap-1.5 w-full">
                      <input
                        type={field.type === 'password' && !showPasswords[`${idx}-${field.key}`] ? 'password' : field.type === 'number' ? 'number' : 'text'}
                        value={
                          String(inst[field.key] ?? '') === '***configured***'
                            ? ''
                            : String(inst[field.key] ?? field.default ?? '')
                        }
                        onChange={(e) => updateInstance(idx, field.key, e.target.value)}
                        placeholder={
                          String(inst[field.key] ?? '') === '***configured***'
                            ? '(configured)'
                            : field.default || (field.required ? 'Required' : 'Optional')
                        }
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
                          onClick={() => setShowPasswords((p) => ({ ...p, [`${idx}-${field.key}`]: !p[`${idx}-${field.key}`] }))}
                          className="p-1.5 rounded transition-all duration-150"
                          style={{ border: '1px solid var(--border)', color: 'var(--text-muted)', backgroundColor: 'var(--bg-primary)' }}
                          title={showPasswords[`${idx}-${field.key}`] ? 'Hide' : 'Show'}
                        >
                          {showPasswords[`${idx}-${field.key}`] ? <EyeOff size={12} /> : <Eye size={12} />}
                        </button>
                      )}
                    </div>
                  </SettingRow>
                ))}

                {/* Path Mapping field */}
                <SettingRow
                  label="Path Mapping"
                  helpText="Map container paths to media server paths, e.g. /media:/data"
                >
                  <input
                    type="text"
                    value={String(inst.path_mapping ?? '')}
                    onChange={(e) => updateInstance(idx, 'path_mapping', e.target.value)}
                    placeholder="/media:/data"
                    className="w-full px-2.5 py-1.5 rounded text-xs transition-all duration-150 focus:outline-none"
                    style={{
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border)',
                      color: 'var(--text-primary)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  />
                </SettingRow>

                {/* Enabled toggle */}
                <SettingRow label="Enabled" helpText="Enable or disable this media server instance.">
                  <Toggle
                    checked={inst.enabled}
                    onChange={() => toggleEnabled(idx)}
                  />
                </SettingRow>

                {/* Action buttons */}
                <div className="flex items-center gap-2 pt-2" style={{ borderTop: '1px solid var(--border)' }}>
                  <button
                    onClick={() => handleTest(idx)}
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
                    Test Connection
                  </button>

                  <button
                    onClick={() => handleSaveInstance(idx)}
                    disabled={saveMut.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
                    style={{ backgroundColor: 'var(--accent)' }}
                  >
                    {saveMut.isPending ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <Save size={12} />
                    )}
                    Save
                  </button>

                  <button
                    onClick={() => removeInstance(idx)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150"
                    style={{
                      border: '1px solid var(--border)',
                      color: 'var(--error)',
                      backgroundColor: 'var(--bg-primary)',
                    }}
                  >
                    <Trash2 size={12} />
                    Remove
                  </button>

                  {/* Test result inline */}
                  {testResult && testResult !== 'testing' && (
                    <span className="text-xs" style={{ color: testResult.healthy ? 'var(--success)' : 'var(--error)' }}>
                      {testResult.healthy ? 'OK' : 'Error'}: {testResult.message}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        )
      })}

      {/* Empty state */}
      {localInstances.length === 0 && (
        <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
          No media servers configured. Add one to enable library refresh notifications after subtitle downloads.
        </div>
      )}
    </div>
  )
}
