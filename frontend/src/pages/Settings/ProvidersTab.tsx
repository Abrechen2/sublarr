import { useState, useEffect } from 'react'
import {
  useProviders, useTestProvider, useProviderStats, useClearProviderCache,
} from '@/hooks/useApi'
import { Loader2, TestTube, ChevronUp, ChevronDown, Trash2, Download, Database } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { SettingRow } from '@/components/shared/SettingRow'
import type { ProviderInfo } from '@/lib/types'

// ─── Field description helper ────────────────────────────────────────────

/**
 * Returns a short German description for a provider config field,
 * keyed first by exact field key, then by normalised label keyword.
 */
function getFieldDescription(key: string, label: string): string {
  // Exact key matches (most specific)
  const byKey: Record<string, string> = {
    opensubtitles_api_key: 'REST API-Key von opensubtitles.com (nicht .org) — unter Account Settings',
    opensubtitles_username: 'OpenSubtitles.org Benutzername (kostenlos registrieren)',
    opensubtitles_password: 'OpenSubtitles.org Passwort',
    subdl_api_key: 'API-Schlüssel von subdl.com — unter Account → API',
    jimaku_api_key: 'API-Schlüssel von jimaku.net — unter Einstellungen → API Token',
  }
  if (byKey[key]) return byKey[key]

  // Label-based fallback (case-insensitive)
  const lbl = label.toLowerCase()
  if (lbl.includes('api key') || lbl.includes('api-key') || lbl.includes('api token')) {
    return 'API-Schlüssel für die Authentifizierung beim Provider'
  }
  if (lbl.includes('username') || lbl.includes('benutzername')) {
    return 'Benutzername des Provider-Kontos'
  }
  if (lbl.includes('password') || lbl.includes('passwort')) {
    return 'Passwort des Provider-Kontos'
  }
  if (lbl.includes('url') || lbl.includes('endpoint')) {
    return 'Basis-URL der Provider-Instanz inkl. Port, ohne abschließenden Slash'
  }
  if (lbl.includes('timeout')) {
    return 'Maximale Wartezeit in Sekunden bis eine Anfrage abgebrochen wird'
  }
  if (lbl.includes('priority') || lbl.includes('priorität')) {
    return 'Niedrigere Zahl = höhere Priorität bei der Provider-Auswahl'
  }
  if (lbl.includes('score') || lbl.includes('threshold') || lbl.includes('schwellenwert')) {
    return 'Mindest-Qualitätsscore für akzeptable Untertitel (0–10)'
  }
  // Generic fallback
  return `Konfigurationswert für „${label}“`
}

// ─── Provider Card Component ────────────────────────────────────────────────

function ProviderCard({
  provider,
  cacheCount,
  values,
  onFieldChange,
  onTest,
  testResult,
  onMoveUp,
  onMoveDown,
  isFirst,
  isLast,
  onToggle,
  onClearCache,
  onReEnable,
}: {
  provider: ProviderInfo
  cacheCount: number
  values: Record<string, string>
  onFieldChange: (key: string, value: string) => void
  onTest: () => void
  testResult?: { healthy: boolean; message: string } | 'testing'
  onMoveUp: () => void
  onMoveDown: () => void
  isFirst: boolean
  isLast: boolean
  onToggle: () => void
  onClearCache: () => void
  onReEnable: () => void
}) {
  const statusColor = !provider.enabled
    ? 'var(--text-muted)'
    : provider.healthy
      ? 'var(--success)'
      : 'var(--error)'

  const statusLabel = !provider.enabled
    ? 'Disabled'
    : provider.initialized
      ? provider.healthy ? 'Healthy' : 'Error'
      : 'Not initialized'

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        opacity: provider.enabled ? 1 : 0.7,
      }}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-semibold capitalize" style={{ color: 'var(--text-primary)' }}>
            {provider.name}
          </span>
          <span
            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium"
            style={{
              backgroundColor: statusColor === 'var(--success)' ? 'var(--success-bg)'
                : statusColor === 'var(--error)' ? 'var(--error-bg)'
                : 'rgba(124,130,147,0.08)',
              color: statusColor,
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: statusColor }}
            />
            {statusLabel}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {/* Enable/Disable toggle with description */}
          <button
            onClick={onToggle}
            className="px-2.5 py-1 rounded text-xs font-medium transition-all duration-150"
            title="Provider für die automatische Untertitel-Suche aktivieren"
            style={{
              backgroundColor: provider.enabled ? 'var(--accent-bg)' : 'var(--bg-primary)',
              color: provider.enabled ? 'var(--accent)' : 'var(--text-muted)',
              border: '1px solid ' + (provider.enabled ? 'var(--accent-dim)' : 'var(--border)'),
            }}
          >
            {provider.enabled ? 'Enabled' : 'Disabled'}
          </button>
            <span
              className="text-[10px] leading-tight text-right"
              style={{ color: 'var(--text-muted)', maxWidth: '160px' }}
            >
              Provider für die automatische Untertitel-Suche aktivieren
            </span>

          {/* Test button */}
          <button
            onClick={onTest}
            disabled={!provider.enabled}
            className="p-1.5 rounded transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
              opacity: provider.enabled ? 1 : 0.5,
            }}
            title="Test provider"
          >
            {testResult === 'testing' ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <TestTube size={14} />
            )}
          </button>

          {/* Priority buttons */}
          <button
            onClick={onMoveUp}
            disabled={isFirst}
            className="p-1.5 rounded transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: isFirst ? 'var(--text-muted)' : 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
            }}
            title="Move up (higher priority)"
          >
            <ChevronUp size={14} />
          </button>
          <button
            onClick={onMoveDown}
            disabled={isLast}
            className="p-1.5 rounded transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: isLast ? 'var(--text-muted)' : 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
            }}
            title="Move down (lower priority)"
          >
            <ChevronDown size={14} />
          </button>
        </div>
      </div>

      {/* Test result */}
      {testResult && testResult !== 'testing' && (
        <div className="text-xs" style={{ color: testResult.healthy ? 'var(--success)' : 'var(--error)' }}>
          Test: {testResult.message}
        </div>
      )}

      {/* Status message */}
      {provider.message && provider.message !== 'OK' && provider.message !== 'Not initialized' && (
        <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {provider.message}
        </div>
      )}

      {/* Stats row */}
      <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--text-secondary)' }}>
        <span className="flex items-center gap-1">
          <Download size={12} />
          {provider.downloads} downloads
        </span>
        <span className="flex items-center gap-1">
          <Database size={12} />
          {cacheCount} cached
        </span>
        {cacheCount > 0 && (
          <button
            onClick={onClearCache}
            className="flex items-center gap-1 transition-all duration-150 hover:opacity-80"
            style={{ color: 'var(--text-muted)' }}
            title="Clear cache for this provider"
          >
            <Trash2 size={11} />
            clear
          </button>
        )}
      </div>

      {/* Health stats */}
      {provider.stats && (
        <div className="space-y-1.5">
          {/* Success rate bar */}
          <div className="flex items-center gap-2">
            <span className="text-xs w-8" style={{ color: 'var(--text-muted)' }}>
              {Math.round(provider.stats.success_rate * 100)}%
            </span>
            <div className="flex-1 h-1.5 rounded-full" style={{ backgroundColor: 'var(--bg-primary)' }}>
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${provider.stats.success_rate * 100}%`,
                  backgroundColor: provider.stats.success_rate > 0.8
                    ? 'rgb(16 185 129)'
                    : provider.stats.success_rate > 0.5
                      ? 'rgb(245 158 11)'
                      : 'rgb(239 68 68)',
                }}
              />
            </div>
          </div>

          {/* Response time and failure info */}
          <div className="flex items-center gap-3 flex-wrap text-xs" style={{ color: 'var(--text-muted)' }}>
            {provider.stats.avg_response_time_ms > 0 && (
              <span>Avg: {Math.round(provider.stats.avg_response_time_ms)}ms</span>
            )}
            {provider.stats.last_response_time_ms > 0 && (
              <span>Last: {Math.round(provider.stats.last_response_time_ms)}ms</span>
            )}
            {provider.stats.consecutive_failures > 0 && (
              <span style={{ color: 'rgb(245 158 11)' }}>
                {provider.stats.consecutive_failures} consecutive failures
              </span>
            )}
          </div>

          {/* Auto-disabled badge with re-enable button */}
          {provider.stats.auto_disabled && (
            <div className="flex items-center gap-2">
              <span
                className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--error-bg)', color: 'var(--error)' }}
              >
                Disabled until {provider.stats.disabled_until
                  ? new Date(provider.stats.disabled_until).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                  : 'unknown'}
              </span>
              <button
                onClick={onReEnable}
                className="px-2 py-0.5 rounded text-xs font-medium transition-all duration-150"
                style={{
                  border: '1px solid var(--accent-dim)',
                  color: 'var(--accent)',
                  backgroundColor: 'var(--accent-bg)',
                }}
              >
                Re-enable
              </button>
            </div>
          )}
        </div>
      )}

      {/* Credential fields rendered with SettingRow for consistent label + description layout */}
      {provider.config_fields.length > 0 && (
        <div className="pt-1" style={{ borderTop: '1px solid var(--border)' }}>
          {provider.config_fields.map((field) => (
            <SettingRow
              key={field.key}
              label={field.label}
              description={getFieldDescription(field.key, field.label)}
            >
              <input
                type={field.type}
                value={values[field.key] === '***configured***' ? '' : (values[field.key] ?? '')}
                onChange={(e) => onFieldChange(field.key, e.target.value)}
                placeholder={values[field.key] === '***configured***' ? '(configured)' : field.required ? 'Required' : 'Optional'}
                className="w-full px-2.5 py-1.5 rounded text-xs transition-all duration-150 focus:outline-none"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono)',
                }}
              />
            </SettingRow>
          ))}
        </div>
      )}
      {provider.config_fields.length === 0 && (
        <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
          No credentials required
        </div>
      )}
    </div>
  )
}

// ─── Providers Tab Content ──────────────────────────────────────────────────

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

  const providers = providersData?.providers ?? []

  // Initialize local priority from provider data
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
    // Build the new providers_enabled list
    const enabledSet = new Set(providers.filter((p) => p.enabled).map((p) => p.name))
    if (currentlyEnabled) {
      enabledSet.delete(name)
    } else {
      enabledSet.add(name)
    }

    // If all are enabled, send empty string (= all enabled by default)
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
        toast(`Cache cleared${providerName ? ` for ${providerName}` : ''}`)
      },
    })
  }

  const handleReEnable = (name: string) => {
    void (async () => {
      try {
        const { enableProvider } = await import('@/api/client')
        const result = await enableProvider(name)
        toast(result.message || `Provider ${name} re-enabled`)
      } catch {
        toast(`Failed to re-enable ${name}`, 'error')
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

  return (
    <div className="space-y-3">
      {/* Global cache clear */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
          {orderedProviders.length} providers configured — drag priority with arrows
        </span>
        <button
          onClick={() => handleClearCache()}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all duration-150"
          style={{
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-primary)',
          }}
        >
          <Trash2 size={12} />
          Clear All Cache
        </button>
      </div>

      {orderedProviders.map((provider, idx) => {
        const cacheCount = statsData?.cache[provider.name]?.total ?? 0
        return (
          <ProviderCard
            key={provider.name}
            provider={provider}
            cacheCount={cacheCount}
            values={values}
            onFieldChange={onFieldChange}
            onTest={() => handleTest(provider.name)}
            testResult={testResults[provider.name]}
            onMoveUp={() => handleMove(idx, 'up')}
            onMoveDown={() => handleMove(idx, 'down')}
            isFirst={idx === 0}
            isLast={idx === orderedProviders.length - 1}
            onToggle={() => handleToggle(provider.name, provider.enabled)}
            onClearCache={() => handleClearCache(provider.name)}
            onReEnable={() => handleReEnable(provider.name)}
          />
        )
      })}
    </div>
  )
}
