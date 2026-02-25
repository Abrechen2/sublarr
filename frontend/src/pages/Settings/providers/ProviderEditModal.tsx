import { useEffect } from 'react'
import { X, Loader2, TestTube, ChevronUp, ChevronDown, Trash2, Download, Database } from 'lucide-react'
import { SettingRow } from '@/components/shared/SettingRow'
import type { ProviderInfo } from '@/lib/types'
import {
  getStatusColor, getStatusLabel, getStatusBg,
  getSuccessRateColor, getFieldDescription,
} from './providerUtils'

interface ProviderEditModalProps {
  provider: ProviderInfo
  cacheCount: number
  priority: number
  isFirst: boolean
  isLast: boolean
  totalProviders: number
  fieldValues: Record<string, string>
  testResult?: { healthy: boolean; message: string } | 'testing'
  onFieldChange: (key: string, value: string) => void
  onTest: () => void
  onToggle: () => void
  onMoveUp: () => void
  onMoveDown: () => void
  onClearCache: () => void
  onReEnable: () => void
  onClose: () => void
}

export function ProviderEditModal({
  provider, cacheCount, priority, isFirst, isLast, totalProviders,
  fieldValues, testResult,
  onFieldChange, onTest, onToggle, onMoveUp, onMoveDown,
  onClearCache, onReEnable, onClose,
}: ProviderEditModalProps) {
  // Escape key closes modal
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  const statusColor = getStatusColor(provider)
  const statusLabel = getStatusLabel(provider)
  const statusBg = getStatusBg(provider)
  const hasStats = provider.stats && provider.stats.total_searches > 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.65)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="w-full max-w-lg flex flex-col rounded-lg overflow-hidden"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          maxHeight: '85vh',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-3 shrink-0"
          style={{ borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        >
          <div>
            <p className="text-[11px] font-medium mb-0.5" style={{ color: 'var(--text-muted)' }}>
              Provider bearbeiten
            </p>
            <p className="text-sm font-semibold capitalize" style={{ color: 'var(--text-primary)' }}>
              {provider.name.replace(/_/g, ' ')}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded transition-colors"
            style={{ color: 'var(--text-muted)' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto flex-1 px-4 py-3 space-y-0">

          {/* ── Aktiviert Toggle ── */}
          <SettingRow
            label="Aktiviert"
            description="Provider für die automatische Untertitel-Suche verwenden"
          >
            <button
              onClick={onToggle}
              className="px-3 py-1.5 rounded text-xs font-medium transition-all duration-150"
              style={{
                backgroundColor: provider.enabled ? 'var(--accent-bg)' : 'var(--bg-primary)',
                color: provider.enabled ? 'var(--accent)' : 'var(--text-muted)',
                border: '1px solid ' + (provider.enabled ? 'var(--accent-dim)' : 'var(--border)'),
              }}
            >
              {provider.enabled ? 'Aktiviert' : 'Deaktiviert'}
            </button>
          </SettingRow>

          {/* ── Status + Fehlermeldung ── */}
          <div className="py-3" style={{ borderBottom: '1px solid var(--border)' }}>
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium"
                style={{ backgroundColor: statusBg, color: statusColor }}
              >
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: statusColor }} />
                {statusLabel}
              </span>
              {/* Test result */}
              {testResult && testResult !== 'testing' && (
                <span
                  className="text-xs"
                  style={{ color: testResult.healthy ? 'var(--success)' : 'var(--error)' }}
                >
                  Test: {testResult.message}
                </span>
              )}
              {testResult === 'testing' && (
                <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                  <Loader2 size={12} className="animate-spin" /> Teste…
                </span>
              )}
            </div>
            {/* Status message (non-trivial) */}
            {provider.message && provider.message !== 'OK' && provider.message !== 'Not initialized' && (
              <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
                {provider.message}
              </p>
            )}
          </div>

          {/* ── Health Stats ── */}
          {provider.enabled && hasStats && (
            <div className="py-3 space-y-2" style={{ borderBottom: '1px solid var(--border)' }}>
              {/* Success rate bar */}
              <div className="flex items-center gap-2">
                <span className="text-[11px] w-8 shrink-0" style={{ color: 'var(--text-muted)' }}>
                  {Math.round(provider.stats.success_rate * 100)}%
                </span>
                <div className="flex-1 h-1.5 rounded-full" style={{ backgroundColor: 'var(--bg-primary)' }}>
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${provider.stats.success_rate * 100}%`,
                      backgroundColor: getSuccessRateColor(provider.stats.success_rate),
                    }}
                  />
                </div>
              </div>
              {/* Response times + failures */}
              <div className="flex items-center gap-3 text-[11px] flex-wrap" style={{ color: 'var(--text-muted)' }}>
                {provider.stats.avg_response_time_ms > 0 && (
                  <span>Ø {Math.round(provider.stats.avg_response_time_ms)}ms</span>
                )}
                {provider.stats.last_response_time_ms > 0 && (
                  <span>Zuletzt: {Math.round(provider.stats.last_response_time_ms)}ms</span>
                )}
                {provider.stats.consecutive_failures > 0 && (
                  <span style={{ color: 'var(--warning)' }}>
                    {provider.stats.consecutive_failures}× Fehler hintereinander
                  </span>
                )}
              </div>
              {/* Auto-disabled */}
              {provider.stats.auto_disabled && (
                <div className="flex items-center gap-2">
                  <span
                    className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                    style={{ backgroundColor: 'color-mix(in srgb, var(--error) 12%, transparent)', color: 'var(--error)' }}
                  >
                    Gesperrt bis{' '}
                    {provider.stats.disabled_until
                      ? new Date(provider.stats.disabled_until).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                      : 'unbekannt'}
                  </span>
                  <button
                    onClick={onReEnable}
                    className="px-2 py-0.5 rounded text-xs font-medium transition-all"
                    style={{
                      border: '1px solid var(--accent-dim)',
                      color: 'var(--accent)',
                      backgroundColor: 'var(--accent-bg)',
                    }}
                  >
                    Reaktivieren
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ── Stats (Downloads + Cache) ── */}
          <div className="py-3 flex items-center gap-4" style={{ borderBottom: '1px solid var(--border)' }}>
            <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
              <Download size={12} />
              {provider.downloads} Downloads
            </span>
            <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
              <Database size={12} />
              {cacheCount} gecacht
            </span>
          </div>

          {/* ── Priorität ── */}
          <SettingRow
            label="Priorität"
            description={`Rang #${priority} von ${totalProviders} — niedriger = höhere Priorität`}
          >
            <div className="flex items-center gap-1.5">
              <button
                onClick={onMoveUp}
                disabled={isFirst}
                className="p-1.5 rounded transition-all"
                style={{
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-primary)',
                  color: isFirst ? 'var(--text-muted)' : 'var(--text-secondary)',
                  opacity: isFirst ? 0.4 : 1,
                }}
                title="Höhere Priorität"
              >
                <ChevronUp size={14} />
              </button>
              <button
                onClick={onMoveDown}
                disabled={isLast}
                className="p-1.5 rounded transition-all"
                style={{
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-primary)',
                  color: isLast ? 'var(--text-muted)' : 'var(--text-secondary)',
                  opacity: isLast ? 0.4 : 1,
                }}
                title="Niedrigere Priorität"
              >
                <ChevronDown size={14} />
              </button>
            </div>
          </SettingRow>

          {/* ── Zugangsdaten ── */}
          {provider.config_fields.length > 0 ? (
            <div className="pt-1" style={{ borderTop: '1px solid var(--border)' }}>
              {provider.config_fields.map((field) => (
                <SettingRow
                  key={field.key}
                  label={field.label}
                  description={getFieldDescription(field.key, field.label)}
                >
                  <input
                    type={field.type}
                    value={fieldValues[field.key] === '***configured***' ? '' : (fieldValues[field.key] ?? '')}
                    onChange={(e) => onFieldChange(field.key, e.target.value)}
                    placeholder={
                      fieldValues[field.key] === '***configured***'
                        ? '(configured)'
                        : field.required
                          ? 'Required'
                          : 'Optional'
                    }
                    className="w-full px-2.5 py-1.5 rounded text-xs transition-all focus:outline-none"
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
          ) : (
            <div className="py-3 text-xs" style={{ color: 'var(--text-muted)', borderTop: '1px solid var(--border)' }}>
              Keine Zugangsdaten erforderlich
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-between px-4 py-3 shrink-0"
          style={{ borderTop: '1px solid var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        >
          {/* Left: Cache clear (conditional) */}
          <div>
            {cacheCount > 0 && (
              <button
                onClick={onClearCache}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all hover:opacity-80"
                style={{
                  border: '1px solid var(--border)',
                  color: 'var(--text-muted)',
                  backgroundColor: 'var(--bg-primary)',
                }}
              >
                <Trash2 size={12} />
                Cache leeren ({cacheCount})
              </button>
            )}
          </div>

          {/* Right: Test + Close */}
          <div className="flex items-center gap-2">
            <button
              onClick={onTest}
              disabled={!provider.enabled || testResult === 'testing'}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all hover:opacity-80"
              style={{
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
                backgroundColor: 'var(--bg-primary)',
                opacity: !provider.enabled || testResult === 'testing' ? 0.5 : 1,
              }}
            >
              {testResult === 'testing' ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <TestTube size={12} />
              )}
              Prüfen
            </button>
            <button
              onClick={onClose}
              className="px-3 py-1.5 rounded text-xs font-medium transition-all hover:opacity-80"
              style={{
                backgroundColor: 'var(--accent)',
                color: 'var(--bg-primary)',
              }}
            >
              Schließen
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
