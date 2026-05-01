import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Loader2, Plus, Trash2 } from 'lucide-react'
import {
  useProviders, useTestProvider, useProviderStats, useClearProviderCache,
} from '@/hooks/useApi'
import { useProviderHealth } from '@/hooks/useProvidersApi'
import { toast } from '@/components/shared/Toast'
import { CollectionLayout } from '@/components/settings/layouts'
import { HealthRail, type HealthItem } from '@/components/settings/primitives'
import type { ProviderInfo } from '@/lib/types'
import { reorderProviders } from './providerUtils'
import { ProviderListItem } from './ProviderListItem'
import { ProviderEditor } from './ProviderEditor'
import { AddProviderModal } from './AddProviderModal'

interface ProvidersCollectionViewProps {
  values: Record<string, string>
  onFieldChange: (key: string, value: string) => void
  onSave: (changed: Record<string, unknown>) => void
}

/**
 * ProvidersCollectionView — Codex Settings Template A reference for the
 * Providers list. Owns selection (URL-addressable via ?id=), drag-drop
 * priority reorder, hide/add and inline editor state. Renders into the
 * CollectionLayout primitive with a HealthRail derived from useProviderHealth.
 */
export function ProvidersCollectionView({
  values, onFieldChange, onSave,
}: ProvidersCollectionViewProps) {
  const { t: tc } = useTranslation('common')

  const { data: providersData, isLoading: providersLoading } = useProviders()
  const { data: statsData } = useProviderStats()
  const { data: healthData } = useProviderHealth()
  const testProviderMut = useTestProvider()
  const clearCacheMut = useClearProviderCache()

  const [testResults, setTestResults] = useState<
    Record<string, { healthy: boolean; message: string } | 'testing'>
  >({})
  const [localPriority, setLocalPriority] = useState<string[] | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [dragFrom, setDragFrom] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState<number | null>(null)

  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('id')

  const providers = useMemo(() => providersData?.providers ?? [], [providersData])

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

  const hiddenNamesRaw = values['providers_hidden'] ?? ''
  const hiddenNames = useMemo(
    () => new Set(
      hiddenNamesRaw ? hiddenNamesRaw.split(',').map((s) => s.trim()).filter(Boolean) : [],
    ),
    [hiddenNamesRaw],
  )

  const shownProviders = orderedProviders.filter((p) => !hiddenNames.has(p.name))
  const hiddenProviders = orderedProviders.filter((p) => hiddenNames.has(p.name))
  const activeCount = shownProviders.filter((p) => p.enabled).length

  // ── URL-addressable selection (Codex convention 5) ─────────────────────────
  const setSelectedId = (id: string | null) => {
    const next = new URLSearchParams(searchParams)
    if (id) next.set('id', id)
    else next.delete('id')
    setSearchParams(next, { replace: true })
  }

  // Auto-select first provider if URL has no ?id= once data arrives
  useEffect(() => {
    if (selectedId === null && shownProviders.length > 0) {
      setSelectedId(shownProviders[0].name)
    }
    // If selected id no longer exists, clear it
    if (selectedId && !shownProviders.some((p) => p.name === selectedId)) {
      setSelectedId(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, shownProviders.length])

  // ── Focus management on selection change (Codex convention 5) ──────────────
  const detailHeadingRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (selectedId && detailHeadingRef.current) {
      detailHeadingRef.current.focus()
    }
  }, [selectedId])

  // ── Mutations ──────────────────────────────────────────────────────────────
  const handleTest = (name: string) => {
    setTestResults((prev) => ({ ...prev, [name]: 'testing' }))
    testProviderMut.mutate(name, {
      onSuccess: (result) => {
        setTestResults((prev) => ({
          ...prev, [name]: { healthy: result.healthy, message: result.message },
        }))
      },
      onError: () => {
        setTestResults((prev) => ({
          ...prev, [name]: { healthy: false, message: 'Test failed' },
        }))
      },
    })
  }

  const handleToggle = (name: string, currentlyEnabled: boolean) => {
    const enabledSet = new Set(providers.filter((p) => p.enabled).map((p) => p.name))
    if (currentlyEnabled) enabledSet.delete(name)
    else enabledSet.add(name)
    const allNames = providers.map((p) => p.name)
    const newValue = enabledSet.size === allNames.length ? '' : Array.from(enabledSet).join(',')
    onSave({ providers_enabled: newValue })
  }

  const handleHide = (name: string) => {
    const newHiddenSet = new Set(hiddenNames)
    newHiddenSet.add(name)
    const enabledSet = new Set(providers.filter((p) => p.enabled).map((p) => p.name))
    enabledSet.delete(name)
    const allNames = providers.map((p) => p.name)
    const newEnabledValue = enabledSet.size === allNames.length ? '' : Array.from(enabledSet).join(',')
    onSave({
      providers_hidden: Array.from(newHiddenSet).join(','),
      providers_enabled: newEnabledValue,
    })
    setSelectedId(null)
    toast(`Provider ${name.replace(/_/g, ' ')} entfernt`)
  }

  const handleAddProvider = (name: string) => {
    const newHiddenSet = new Set(hiddenNames)
    newHiddenSet.delete(name)
    const enabledSet = new Set(providers.filter((p) => p.enabled).map((p) => p.name))
    enabledSet.add(name)
    const allNames = providers.map((p) => p.name)
    const newEnabledValue = enabledSet.size === allNames.length ? '' : Array.from(enabledSet).join(',')
    onSave({
      providers_hidden: Array.from(newHiddenSet).join(','),
      providers_enabled: newEnabledValue,
    })
    setSelectedId(name)
    setShowAddModal(false)
  }

  const handleClearCache = (providerName?: string) => {
    clearCacheMut.mutate(providerName, {
      onSuccess: () => toast(`Cache geleert${providerName ? ` für ${providerName}` : ''}`),
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

  // ── Drag-drop reorder (vertical list) ──────────────────────────────────────
  const handleDragStart = (e: React.DragEvent, index: number) => {
    setDragFrom(index)
    e.dataTransfer.effectAllowed = 'move'
  }
  const handleDragOverItem = (e: React.DragEvent, index: number) => {
    e.preventDefault()
    setDragOver(index)
  }
  const handleDrop = (e: React.DragEvent, toIndex: number) => {
    e.preventDefault()
    if (dragFrom === null || dragFrom === toIndex) {
      setDragFrom(null); setDragOver(null); return
    }
    const current = localPriority ?? providers.map((p) => p.name)
    const reordered = reorderProviders(current, dragFrom, toIndex)
    setLocalPriority(reordered)
    onSave({ provider_priorities: reordered.join(',') })
    setDragFrom(null); setDragOver(null)
  }
  const handleDragEnd = () => { setDragFrom(null); setDragOver(null) }

  // ── HealthRail items derived from useProviderHealth ────────────────────────
  const healthByName = useMemo(() => {
    const map = new Map<string, NonNullable<typeof healthData>['providers'][number]>()
    for (const h of healthData?.providers ?? []) map.set(h.name, h)
    return map
  }, [healthData])

  const healthItems = useMemo<HealthItem[]>(() => {
    if (!healthData) return []
    const items: HealthItem[] = []
    for (const p of shownProviders) {
      const h = healthByName.get(p.name)
      if (!h) continue
      const cbState = h.circuit_breaker_state ?? 'closed'
      const isRateLimited = h.throttle_reason === 'rate_limited'
      if (!h.healthy) {
        items.push({
          id: `provider-${p.name}-unhealthy`,
          severity: 'err',
          title: `${p.name.replace(/_/g, ' ')} unhealthy`,
          body: cbState !== 'closed' ? `Circuit: ${cbState}` : undefined,
          fix: { onClick: () => setSelectedId(p.name), label: 'Inspect →' },
        })
      } else if (isRateLimited) {
        items.push({
          id: `provider-${p.name}-rate-limited`,
          severity: 'warn',
          title: `${p.name.replace(/_/g, ' ')} rate limited`,
          fix: { onClick: () => setSelectedId(p.name), label: 'Inspect →' },
        })
      } else if (cbState !== 'closed') {
        items.push({
          id: `provider-${p.name}-circuit`,
          severity: 'warn',
          title: `${p.name.replace(/_/g, ' ')} circuit ${cbState}`,
          fix: { onClick: () => setSelectedId(p.name), label: 'Inspect →' },
        })
      } else {
        items.push({
          id: `provider-${p.name}-ok`,
          severity: 'ok',
          title: `${p.name.replace(/_/g, ' ')} healthy`,
        })
      }
    }
    return items
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [healthData, healthByName, shownProviders])

  if (providersLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  const listHeader = (
    <div className="flex items-center justify-between gap-2">
      <div className="text-[11px] font-medium" style={{ color: 'var(--text-secondary)' }}>
        {activeCount} aktiv / {shownProviders.length} konfiguriert
      </div>
      <div className="flex items-center gap-1">
        <button
          onClick={() => setShowAddModal(true)}
          data-testid="settings.providers.add"
          className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-all hover:opacity-80"
          style={{
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-primary)',
          }}
          disabled={hiddenProviders.length === 0}
          aria-label={tc('ui.add_provider')}
        >
          <Plus size={11} /> {tc('ui.add_provider')}
        </button>
        <button
          onClick={() => handleClearCache()}
          data-testid="settings.providers.clear-cache"
          className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-all hover:opacity-80"
          style={{
            border: '1px solid var(--border)',
            color: 'var(--text-muted)',
            backgroundColor: 'var(--bg-primary)',
          }}
          aria-label="Clear all caches"
          title="Alle Caches leeren"
        >
          <Trash2 size={11} />
        </button>
      </div>
    </div>
  )

  const emptyDetail = (
    <div
      data-testid="settings.providers.empty-detail"
      className="flex items-center justify-center h-full text-xs text-muted"
    >
      Wähle einen Provider aus der Liste oder klicke auf „+ Hinzufügen“.
    </div>
  )

  return (
    <div data-testid="settings.providers.collection-view">
      <CollectionLayout
        items={shownProviders}
        selectedId={selectedId}
        getItemId={(p) => p.name}
        listHeader={listHeader}
        renderListItem={(provider, isActive) => {
          const idx = shownProviders.indexOf(provider)
          return (
            <div
              draggable
              onDragStart={(e) => handleDragStart(e, idx)}
              onDragOver={(e) => handleDragOverItem(e, idx)}
              onDrop={(e) => handleDrop(e, idx)}
              onDragEnd={handleDragEnd}
              data-testid={`settings.providers.list-item.${provider.name}`}
            >
              <ProviderListItem
                provider={provider}
                priority={idx + 1}
                isActive={isActive}
                isDragging={dragFrom === idx}
                isDragOver={dragOver === idx}
              />
            </div>
          )
        }}
        renderDetail={(provider) => {
          if (!provider) return emptyDetail
          const fieldValues = Object.fromEntries(
            (provider.config_fields ?? []).map((f) => [f.key, values[f.key] ?? '']),
          )
          return (
            <div
              ref={detailHeadingRef}
              tabIndex={-1}
              data-testid={`settings.providers.detail.${provider.name}`}
            >
              <ProviderEditor
                provider={provider}
                cacheCount={statsData?.cache[provider.name]?.total ?? 0}
                fieldValues={fieldValues}
                testResult={testResults[provider.name]}
                onFieldChange={onFieldChange}
                onTest={() => handleTest(provider.name)}
                onToggle={() => handleToggle(provider.name, provider.enabled)}
                onClearCache={() => handleClearCache(provider.name)}
                onReEnable={() => handleReEnable(provider.name)}
                onRemove={() => handleHide(provider.name)}
              />
            </div>
          )
        }}
        onSelect={setSelectedId}
        emptyState={
          <div
            data-testid="settings.providers.empty-list"
            className="text-[11px] text-muted px-3 py-2"
          >
            Noch kein Provider konfiguriert.
          </div>
        }
        healthRail={healthItems.length > 0 ? <HealthRail items={healthItems} /> : undefined}
      />

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
