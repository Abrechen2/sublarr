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

  if (providersLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  const editingProviderData = editingProvider
    ? orderedProviders.find((p) => p.name === editingProvider) ?? null
    : null
  const editingProviderIdx = editingProviderData
    ? orderedProviders.indexOf(editingProviderData)
    : -1

  const disabledProviders = orderedProviders.filter((p) => !p.enabled)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {orderedProviders.length} Provider konfiguriert
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
        {orderedProviders.map((provider, idx) => (
          <ProviderTile
            key={provider.name}
            provider={provider}
            cacheCount={statsData?.cache[provider.name]?.total ?? 0}
            priority={idx + 1}
            testResult={testResults[provider.name]}
            onOpenEdit={() => setEditingProvider(provider.name)}
          />
        ))}

        {/* "+" Tile — only if disabled providers exist */}
        {disabledProviders.length > 0 && (
          <button
            onClick={() => setShowAddModal(true)}
            className="h-24 flex flex-col items-center justify-center gap-1 rounded transition-all duration-150"
            style={{
              border: '2px dashed var(--border)',
              color: 'var(--text-muted)',
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
            <span className="text-[11px] font-medium">Provider aktivieren</span>
          </button>
        )}
      </div>

      {/* Edit Modal */}
      {editingProviderData && (
        <ProviderEditModal
          provider={editingProviderData}
          cacheCount={statsData?.cache[editingProviderData.name]?.total ?? 0}
          priority={editingProviderIdx + 1}
          isFirst={editingProviderIdx === 0}
          isLast={editingProviderIdx === orderedProviders.length - 1}
          totalProviders={orderedProviders.length}
          fieldValues={Object.fromEntries(
            editingProviderData.config_fields.map((f) => [f.key, values[f.key] ?? ''])
          )}
          testResult={testResults[editingProviderData.name]}
          onFieldChange={onFieldChange}
          onTest={() => handleTest(editingProviderData.name)}
          onToggle={() => handleToggle(editingProviderData.name, editingProviderData.enabled)}
          onMoveUp={() => handleMove(editingProviderIdx, 'up')}
          onMoveDown={() => handleMove(editingProviderIdx, 'down')}
          onClearCache={() => handleClearCache(editingProviderData.name)}
          onReEnable={() => handleReEnable(editingProviderData.name)}
          onClose={() => setEditingProvider(null)}
        />
      )}

      {/* Add Modal */}
      {showAddModal && (
        <AddProviderModal
          disabledProviders={disabledProviders}
          onSelect={(name) => {
            handleToggle(name, false)
            setEditingProvider(name)
            setShowAddModal(false)
          }}
          onClose={() => setShowAddModal(false)}
        />
      )}
    </div>
  )
}
