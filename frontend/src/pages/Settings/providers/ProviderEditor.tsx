import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, TestTube, Trash2, Download, Database } from 'lucide-react'
import { SettingRow } from '@/components/shared/SettingRow'
import ProviderKeysPool from '@/components/settings/ProviderKeysPool'
import type { ProviderInfo } from '@/lib/types'
import {
  getStatusColor, getStatusLabel, getStatusBg,
  getSuccessRateColor, getFieldDescription,
} from './providerUtils'

export interface ProviderEditorProps {
  provider: ProviderInfo
  cacheCount: number
  fieldValues: Record<string, string>
  testResult?: { healthy: boolean; message: string } | 'testing'
  onFieldChange: (key: string, value: string) => void
  onTest: () => void
  /** Fetch one real subtitle. Costs the account a download, so it is a
   *  separate action rather than part of the ordinary test. */
  onTestDownload?: () => void
  onToggle: () => void
  onClearCache: () => void
  onReEnable: () => void
  onRemove?: () => void
  /** Optional content rendered in the header next to the title (e.g. modal close button). */
  headerExtra?: React.ReactNode
  /** Optional content appended to the footer (right-aligned, e.g. modal close button). */
  footerExtra?: React.ReactNode
  /** When true, the page-level title row is hidden — used inside ProviderEditModal which has its own title. */
  hideTitle?: boolean
}

/**
 * ProviderEditor — inline provider configuration form.
 *
 * Extracted from ProviderEditModal so the same body can be rendered inline
 * inside CollectionLayout's detail pane (Codex Settings Template A) without
 * the modal chrome. ProviderEditModal now wraps this component.
 */
export function ProviderEditor({
  provider, cacheCount, fieldValues, testResult,
  onFieldChange, onTest, onTestDownload, onToggle, onClearCache, onReEnable, onRemove,
  headerExtra, footerExtra, hideTitle,
}: ProviderEditorProps) {
  const { t: tc } = useTranslation('common')
  const { t: ts } = useTranslation('settings')
  const [confirmRemove, setConfirmRemove] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  const validateField = (fieldKey: string, value: string, label: string) => {
    if (!value.trim()) {
      setErrors(prev => ({ ...prev, [fieldKey]: ts('providers_tab.editor.field_required_error', { label }) }))
    } else {
      setErrors(prev => {
        const { [fieldKey]: _removed, ...rest } = prev
        return rest
      })
    }
  }

  const configFields = provider.config_fields ?? []

  const handleTest = () => {
    const newErrors: Record<string, string> = {}
    for (const field of configFields) {
      if (field.required) {
        const value = fieldValues[field.key] ?? ''
        if (value !== '***configured***' && !value.trim()) {
          newErrors[field.key] = ts('providers_tab.editor.field_required_error', { label: field.label })
        }
      }
    }
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }
    onTest()
  }

  const statusColor = getStatusColor(provider)
  const statusLabel = getStatusLabel(provider, ts)
  const statusBg = getStatusBg(provider)
  const hasStats = provider.stats && provider.stats.total_searches > 0
  // The status pill row duplicates the toggle button when the provider is
  // plainly disabled with nothing else to report. Hide it in that case so the
  // detail pane has exactly one source of truth for the on/off state.
  const hasMessage =
    !!provider.message && provider.message !== 'OK' && provider.message !== 'Not initialized'
  const showStatusRow =
    provider.enabled || provider.stats?.auto_disabled || !!testResult || hasMessage

  return (
    <div data-testid={`provider-editor-${provider.name}`} className="flex flex-col">
      {/* Title row */}
      {!hideTitle && (
        <div className="flex items-center justify-between mb-3 pb-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <h2 className="text-sm font-semibold capitalize m-0" style={{ color: 'var(--text-primary)' }}>
            {provider.name.replace(/_/g, ' ')}
          </h2>
          {headerExtra}
        </div>
      )}

      {/* Body */}
      <div className="space-y-0">
        {/* Enabled toggle */}
        <SettingRow
          label={tc('ui.enabled')}
          description={ts('providers_tab.editor.enable_hint')}
        >
          <button
            onClick={onToggle}
            data-testid={`provider-editor-${provider.name}-toggle`}
            className="px-3 py-1.5 rounded text-xs font-medium transition-all duration-150"
            style={{
              backgroundColor: provider.enabled ? 'var(--accent-bg)' : 'var(--bg-primary)',
              color: provider.enabled ? 'var(--accent)' : 'var(--text-muted)',
              border: '1px solid ' + (provider.enabled ? 'var(--accent-dim)' : 'var(--border)'),
            }}
          >
            {provider.enabled ? ts('providers_tab.enabled') : ts('providers_tab.disabled')}
          </button>
        </SettingRow>

        {/* Status + error message */}
        {showStatusRow && (
          <div className="py-3" style={{ borderBottom: '1px solid var(--border)' }}>
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium"
                style={{ backgroundColor: statusBg, color: statusColor }}
              >
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: statusColor }} />
                {statusLabel}
              </span>
              {testResult && testResult !== 'testing' && (
                <span
                  className="text-xs"
                  style={{ color: testResult.healthy ? 'var(--success)' : 'var(--error)' }}
                >
                  {ts('providers_tab.editor.test_label')}: {testResult.message}
                </span>
              )}
              {testResult === 'testing' && (
                <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                  <Loader2 size={12} className="animate-spin" /> {ts('providers_tab.editor.testing')}
                </span>
              )}
            </div>
            {hasMessage && (
              <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
                {provider.message}
              </p>
            )}
          </div>
        )}

        {/* Health stats — two stacked bars (since 0.92.0-beta):
            • Treffer-Quote (result_rate)   = Anteil Suchen mit Treffern vom Provider
            • Download-Quote (download_rate) = Anteil Suchen wo wir den Treffer gewählt haben
            success_rate is kept as a back-compat alias for download_rate so older
            cached provider responses don't crash the UI. */}
        {provider.enabled && hasStats && (
          <div className="py-3 space-y-2" style={{ borderBottom: '1px solid var(--border)' }}>
            <div className="flex items-center gap-2">
              <span className="text-[11px] w-8 shrink-0" style={{ color: 'var(--text-muted)' }}>
                {Math.round((provider.stats.result_rate ?? 0) * 100)}%
              </span>
              <div
                className="flex-1 h-1.5 rounded-full"
                style={{ backgroundColor: 'var(--bg-primary)' }}
                title={`${ts('providers_tab.editor.result_rate', 'Treffer-Quote')}: ${Math.round((provider.stats.result_rate ?? 0) * 100)}%`}
              >
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${(provider.stats.result_rate ?? 0) * 100}%`,
                    backgroundColor: 'var(--accent)',
                  }}
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] w-8 shrink-0" style={{ color: 'var(--text-muted)' }}>
                {Math.round((provider.stats.download_rate ?? provider.stats.success_rate) * 100)}%
              </span>
              <div
                className="flex-1 h-1.5 rounded-full"
                style={{ backgroundColor: 'var(--bg-primary)' }}
                title={`${ts('providers_tab.editor.download_rate', 'Download-Quote')}: ${Math.round((provider.stats.download_rate ?? provider.stats.success_rate) * 100)}%`}
              >
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${(provider.stats.download_rate ?? provider.stats.success_rate) * 100}%`,
                    backgroundColor: getSuccessRateColor(
                      provider.stats.download_rate ?? provider.stats.success_rate,
                    ),
                  }}
                />
              </div>
            </div>
            <div className="flex items-center gap-3 text-[11px] flex-wrap" style={{ color: 'var(--text-muted)' }}>
              {provider.stats.avg_response_time_ms > 0 && (
                <span>Ø {Math.round(provider.stats.avg_response_time_ms)}ms</span>
              )}
              {provider.stats.last_response_time_ms > 0 && (
                <span>{ts('providers_tab.editor.last_response')}: {Math.round(provider.stats.last_response_time_ms)}ms</span>
              )}
              {provider.stats.consecutive_failures > 0 && (
                <span style={{ color: 'var(--warning)' }}>
                  {ts('providers_tab.editor.consecutive_failures', { count: provider.stats.consecutive_failures })}
                </span>
              )}
            </div>
            {provider.stats.auto_disabled && (
              <div className="flex items-center gap-2">
                <span
                  className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                  style={{ backgroundColor: 'color-mix(in srgb, var(--error) 12%, transparent)', color: 'var(--error)' }}
                >
                  {ts('providers_tab.editor.locked_until')}{' '}
                  {provider.stats.disabled_until
                    ? new Date(provider.stats.disabled_until).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    : ts('providers_tab.editor.unknown')}
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
                  {ts('providers_tab.re_enable')}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Stats: downloads + cache */}
        <div className="py-3 flex items-center gap-4" style={{ borderBottom: '1px solid var(--border)' }}>
          <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
            <Download size={12} />
            {ts('providers_tab.editor.downloads_count', { count: provider.downloads })}
          </span>
          <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
            <Database size={12} />
            {ts('providers_tab.editor.cached_count', { count: cacheCount })}
          </span>
        </div>

        {/* Credentials */}
        {configFields.length > 0 ? (
          <div className="pt-1">
            {configFields.map((field) => {
              const inputId = `provider-edit-${provider.name}-${field.key}`
              const errorId = `${inputId}-error`
              const hasError = !!errors[field.key]
              return (
                <SettingRow
                  key={field.key}
                  label={field.label}
                  description={getFieldDescription(field.key, field.label, ts)}
                  htmlFor={inputId}
                >
                  <div className="w-full">
                    <input
                      id={inputId}
                      type={field.type}
                      value={fieldValues[field.key] === '***configured***' ? '' : (fieldValues[field.key] ?? '')}
                      onChange={(e) => onFieldChange(field.key, e.target.value)}
                      onBlur={(e) => {
                        if (field.required && fieldValues[field.key] !== '***configured***') {
                          validateField(field.key, e.target.value, field.label)
                        }
                      }}
                      placeholder={
                        fieldValues[field.key] === '***configured***'
                          ? ts('providers_tab.editor.configured')
                          : field.required
                            ? ts('providers_tab.editor.required_field')
                            : ts('providers_tab.editor.optional_field')
                      }
                      aria-describedby={hasError ? errorId : undefined}
                      aria-invalid={hasError}
                      className="w-full px-2.5 py-1.5 rounded text-xs transition-all focus:outline-none"
                      style={{
                        backgroundColor: 'var(--bg-primary)',
                        border: `1px solid ${hasError ? 'var(--error)' : 'var(--border)'}`,
                        color: 'var(--text-primary)',
                        fontFamily: 'var(--font-mono)',
                      }}
                    />
                    {hasError && (
                      <p id={errorId} role="alert" className="text-xs mt-1" style={{ color: 'var(--error)' }}>
                        {errors[field.key]}
                      </p>
                    )}
                  </div>
                </SettingRow>
              )
            })}
          </div>
        ) : (
          <div className="py-3 text-xs" style={{ color: 'var(--text-muted)' }}>
            {ts('providers_tab.editor.no_credentials_required')}
          </div>
        )}

        {/* Multi-key pool */}
        <ProviderKeysPool providerName={provider.name} />
      </div>

      {/* Footer */}
      <div
        className="flex items-center justify-between mt-4 pt-3 gap-2 flex-wrap"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          {onRemove && !confirmRemove && (
            <button
              onClick={() => setConfirmRemove(true)}
              data-testid={`provider-editor-${provider.name}-remove`}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all hover:opacity-80"
              style={{
                border: '1px solid color-mix(in srgb, var(--error) 40%, var(--border))',
                color: 'var(--error)',
                backgroundColor: 'var(--bg-primary)',
              }}
            >
              <Trash2 size={12} />
              {tc('ui.remove')}
            </button>
          )}
          {onRemove && confirmRemove && (
            <div className="flex items-center gap-1.5">
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{tc('ui.are_you_sure')}</span>
              <button
                onClick={onRemove}
                className="px-2.5 py-1.5 rounded text-xs font-medium"
                style={{ backgroundColor: 'var(--error)', color: 'white' }}
              >
                {tc('confirm.yes')}
              </button>
              <button
                onClick={() => setConfirmRemove(false)}
                className="px-2.5 py-1.5 rounded text-xs font-medium"
                style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
              >
                {tc('confirm.no')}
              </button>
            </div>
          )}
          {!confirmRemove && cacheCount > 0 && (
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
              {ts('providers_tab.editor.cache')} ({cacheCount})
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleTest}
            disabled={!provider.enabled || testResult === 'testing'}
            data-testid={`provider-editor-${provider.name}-test`}
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
            {tc('actions.test')}
          </button>
          {onTestDownload && (
            <button
              onClick={onTestDownload}
              disabled={!provider.enabled || testResult === 'testing'}
              data-testid={`provider-editor-${provider.name}-test-download`}
              title={ts('providers_tab.editor.test_download_hint')}
              className="flex items-center gap-1.5 rounded border border-border bg-primary px-3 py-1.5 text-xs font-medium text-secondary transition-all hover:opacity-80 disabled:opacity-50"
            >
              <Download size={12} />
              {ts('providers_tab.editor.test_download')}
            </button>
          )}
          {footerExtra}
        </div>
      </div>
    </div>
  )
}
