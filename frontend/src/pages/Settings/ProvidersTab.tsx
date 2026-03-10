import { useState, useEffect } from 'react'
import {
  useProviders, useTestProvider, useProviderStats, useClearProviderCache,
} from '@/hooks/useApi'
import { Loader2, Trash2, Plus } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import type { ProviderInfo } from '@/lib/types'
import { ProviderTile } from './providers/ProviderTile'
import { ProviderEditModal } from './providers/ProviderEditModal'
import { AddProviderModal } from './providers/AddProviderModal'

export function ProvidersTab({
  values,
  onFieldChange,
  onSave,
}: {
  values: Record<string, string>
  onFieldChange: (key: string, value: string) => void
  onSave: (changed: Record<string, unknown>) => void
}) {
  const { data: providersData, isLoading: providersLoading } = useProviders()
  const { data: statsData } = useProviderStats()
  const testProviderMut = useTestProvider()
  const clearCacheMut = useClearProviderCache()
  const [testResults, setTestResults] = useState<Record<string, { healthy: boolean; message: string } | 'testing'>>({})
  const [localPriority, setLocalPriority] = useState<string[] | null>(null)
  const [editingProvider, setEditingProvider] = useState<string | null>(null)
  const [isNewProvider, setIsNewProvider] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)

  const providers = providersData?.providers ?? []

  useEffect(() => {
    if (providers.length > 0 && localPriority === null) {
      setLocalPriority(providers.map((p) => p.name))
    }
  }, [providers, localPriority])

  const orderedProviders = localPriority
    ? localPriority
        .map((name) => providers.find((p) => p.name === name))
        .filter((p): p is ProviderInfo => p !== undefined)
    : providers

  // providers_hidden: comma-separated names that are truly removed from the grid
  const hiddenNamesRaw = values['providers_hidden'] ?? ''
  const hiddenNames = new Set(
    hiddenNamesRaw ? hiddenNamesRaw.split(',').map((s) => s.trim()).filter(Boolean) : []
  )

  // Grid shows all non-hidden providers (both enabled AND disabled)
  const shownProviders = orderedProviders.filter((p) => !hiddenNames.has(p.name))
  // + modal shows only hidden/removed providers
  const hiddenProviders = orderedProviders.filter((p) => hiddenNames.has(p.name))

  const activeCount = shownProviders.filter((p) => p.enabled).length

  const handleTest = (name: string) => {
    setTestResults((prev) => ({ ...prev, [name]: 'testing' }))
    testProviderMut.mutate(name, {
      onSuccess: (result) => {
        setTestResults((prev) => ({ ...prev, [name]: { healthy: result.healthy, message: result.message } }))
      },
      onError: () => {
        setTestResults((prev) => ({ ...prev, [name]: { healthy: false, message: 'Test failed' } }))
      },
    })
  }

  const handleToggle = (name: string, currentlyEnabled: boolean) => {
    const enabledSet = new Set(providers.filter((p) => p.enabled).map((p) => p.name))
    if (currentlyEnabled) {
      enabledSet.delete(name)
    } else {
      enabledSet.add(name)
    }
    const allNames = providers.map((p) => p.name)
    const newValue = enabledSet.size === allNames.length ? '' : Array.from(enabledSet).join(',')
    onSave({ providers_enabled: newValue })
  }

  // Entfernen: adds to providers_hidden AND disables in providers_enabled
  const handleHide = (name: string) => {
    const newHiddenSet = new Set(hiddenNames)
    newHiddenSet.add(name)
    const newHiddenValue = Array.from(newHiddenSet).join(',')

    const enabledSet = new Set(providers.filter((p) => p.enabled).map((p) => p.name))
    enabledSet.delete(name)
    const allNames = providers.map((p) => p.name)
    const newEnabledValue = enabledSet.size === allNames.length ? '' : Array.from(enabledSet).join(',')

    onSave({ providers_hidden: newHiddenValue, providers_enabled: newEnabledValue })
    setEditingProvider(null)
    setIsNewProvider(false)
    toast(`Provider ${name.replace(/_/g, ' ')} entfernt`)
  }

  // Hinzufügen: removes from providers_hidden AND enables in providers_enabled
  const handleAddProvider = (name: string) => {
    const newHiddenSet = new Set(hiddenNames)
    newHiddenSet.delete(name)
    const newHiddenValue = Array.from(newHiddenSet).join(',')

    const enabledSet = new Set(providers.filter((p) => p.enabled).map((p) => p.name))
    enabledSet.add(name)
    const allNames = providers.map((p) => p.name)
    const newEnabledValue = enabledSet.size === allNames.length ? '' : Array.from(enabledSet).join(',')

    onSave({ providers_hidden: newHiddenValue, providers_enabled: newEnabledValue })
    setEditingProvider(name)
    setIsNewProvider(true)
    setShowAddModal(false)
  }

  const handleMove = (index: number, direction: 'up' | 'down') => {
    if (!localPriority) return
    const newOrder = [...localPriority]
    const swapIdx = direction === 'up' ? index - 1 : index + 1
    if (swapIdx < 0 || swapIdx >= newOrder.length) return
    ;[newOrder[index], newOrder[swapIdx]] = [newOrder[swapIdx], newOrder[index]]
    setLocalPriority(newOrder)
    onSave({ provider_priorities: newOrder.join(',') })
  }

  const handleClearCache = (providerName?: string) => {
    clearCacheMut.mutate(providerName, {
      onSuccess: () => {
        toast(`Cache geleert${providerName ? ` für ${providerName}` : ''}`)
      },
    })
  }

  const handleReEnable = (name: string) => {
    void (async () => {
      try {
        const { enableProvider } = await import('@/api/client')
        const result = await enableProvider(name)
        toast(result.message || `Provider ${name} reaktiviert`)
      } catch {
        toast(`Fehler beim Reaktivieren von ${name}`, 'error')
      }
    })()
  }

  const handleCloseEdit = () => {
    setEditingProvider(null)
    setIsNewProvider(false)
  }

  if (providersLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  const editingProviderData = editingProvider
    ? shownProviders.find((p) => p.name === editingProvider) ?? null
    : null
  const editingProviderIdx = editingProviderData
    ? shownProviders.indexOf(editingProviderData)
    : -1

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {activeCount} aktiv / {shownProviders.length} konfiguriert
        </span>
        <button
          onClick={() => handleClearCache()}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all duration-150 hover:opacity-80"
          style={{
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-primary)',
          }}
        >
          <Trash2 size={12} />
          Gesamten Cache leeren
        </button>
      </div>

      {/* Tile Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {shownProviders.map((provider, idx) => (
          <ProviderTile
            key={provider.name}
            provider={provider}
            cacheCount={statsData?.cache[provider.name]?.total ?? 0}
            priority={idx + 1}
            testResult={testResults[provider.name]}
            onOpenEdit={() => setEditingProvider(provider.name)}
            onToggle={() => handleToggle(provider.name, provider.enabled)}
            onRemove={() => handleHide(provider.name)}
          />
        ))}

        {/* Empty state */}
        {shownProviders.length === 0 && (
          <div
            className="col-span-full py-10 text-center text-sm"
            style={{ color: 'var(--text-muted)' }}
          >
            Noch kein Provider konfiguriert — klicke auf + um einen hinzuzufügen.
          </div>
        )}

        {/* "+" tile — shows when there are hidden providers to re-add */}
        {hiddenProviders.length > 0 && (
          <button
            onClick={() => setShowAddModal(true)}
            className="flex flex-col items-center justify-center gap-1 rounded transition-all duration-150"
            style={{
              border: '2px dashed var(--border)',
              color: 'var(--text-muted)',
              minHeight: '7rem',
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
            <Plus size={22} />
            <span className="text-[11px] font-medium">Provider hinzufügen</span>
          </button>
        )}
      </div>

      {/* Anti-Captcha Section */}
      <div
        className="rounded-lg p-4 space-y-3"
        style={{ border: '1px solid var(--border)', backgroundColor: 'var(--bg-surface)' }}
      >
        <div>
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Anti-Captcha</h3>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Automatically solve captcha challenges from providers like Kitsunekko.
            Supports Anti-Captcha.com and CapMonster.
          </p>
        </div>
        <div className="grid grid-cols-[160px_1fr] items-center gap-3">
          <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Backend</label>
          <select
            value={values['anti_captcha_provider'] ?? ''}
            onChange={(e) => onFieldChange('anti_captcha_provider', e.target.value)}
            className="px-2 py-1.5 rounded text-xs"
            style={{
              border: '1px solid var(--border)',
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-primary)',
            }}
          >
            <option value="">Disabled</option>
            <option value="anticaptcha">Anti-Captcha.com</option>
            <option value="capmonster">CapMonster</option>
          </select>
        </div>
        {values['anti_captcha_provider'] && (
          <div className="grid grid-cols-[160px_1fr] items-center gap-3">
            <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>API Key</label>
            <input
              type="password"
              value={values['anti_captcha_api_key'] ?? ''}
              onChange={(e) => onFieldChange('anti_captcha_api_key', e.target.value)}
              placeholder="Your API key"
              className="px-2 py-1.5 rounded text-xs"
              style={{
                border: '1px solid var(--border)',
                backgroundColor: 'var(--bg-primary)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
        )}
      </div>

      {/* Edit Modal */}
      {editingProviderData && (
        <ProviderEditModal
          provider={editingProviderData}
          cacheCount={statsData?.cache[editingProviderData.name]?.total ?? 0}
          priority={editingProviderIdx + 1}
          isFirst={editingProviderIdx === 0}
          isLast={editingProviderIdx === shownProviders.length - 1}
          totalProviders={shownProviders.length}
          fieldValues={Object.fromEntries(
            editingProviderData.config_fields.map((f) => [f.key, values[f.key] ?? ''])
          )}
          testResult={testResults[editingProviderData.name]}
          isNew={isNewProvider}
          onFieldChange={onFieldChange}
          onTest={() => handleTest(editingProviderData.name)}
          onToggle={() => handleToggle(editingProviderData.name, editingProviderData.enabled)}
          onMoveUp={() => handleMove(editingProviderIdx, 'up')}
          onMoveDown={() => handleMove(editingProviderIdx, 'down')}
          onClearCache={() => handleClearCache(editingProviderData.name)}
          onReEnable={() => handleReEnable(editingProviderData.name)}
          onRemove={() => handleHide(editingProviderData.name)}
          onClose={handleCloseEdit}
        />
      )}

      {/* Add Modal — shows removed/hidden providers */}
      {showAddModal && (
        <AddProviderModal
          availableProviders={hiddenProviders}
          onSelect={handleAddProvider}
          onClose={() => setShowAddModal(false)}
        />
      )}
    </div>
  )
}
