import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Save, Loader2, TestTube, ChevronUp, ChevronDown, Activity, Eye, EyeOff } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { SettingRow } from '@/components/shared/SettingRow'
import { useBackendConfig, useSaveBackendConfig } from '@/hooks/useApi'
import { useTranslationConcurrency } from '@/hooks/useTranslationCost'
import { useTranslationMutations } from '@/hooks/useTranslationMutations'
import type { TranslationBackendInfo, BackendStats, BackendHealthResult } from '@/lib/types'

// ─── Translation Backend Card ────────────────────────────────────────────────

export function BackendCard({
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
  const { t } = useTranslation('settings')
  const [expanded, setExpanded] = useState(false)
  const [formValues, setFormValues] = useState<Record<string, string>>({})
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})
  const { data: configData } = useBackendConfig(expanded ? backend.name : '')
  const saveConfigMut = useSaveBackendConfig()

  // Phase A1: concurrency slider (persisted per-backend).
  const { data: conc } = useTranslationConcurrency()
  const { setConcurrency: setConcMut } = useTranslationMutations()
  const currentLimit =
    conc?.backends.find((b) => b.backend === backend.name)?.limit ?? 3
  const [draftLimit, setDraftLimit] = useState(currentLimit)

  useEffect(() => {
    setDraftLimit(currentLimit)
  }, [currentLimit])

  // Debounce slider saves (500 ms) so rapid drags emit a single PATCH.
  useEffect(() => {
    const h = setTimeout(() => {
      if (
        draftLimit !== currentLimit &&
        draftLimit >= 1 &&
        draftLimit <= 50
      ) {
        setConcMut.mutate({ backend: backend.name, limit: draftLimit })
      }
    }, 500)
    return () => clearTimeout(h)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftLimit])

  // Load config values when expanded
  useEffect(() => {
    if (configData) {
      setFormValues(configData)
    }
  }, [configData])

  const getFieldDescription = (key: string): string | undefined => {
    const k = key.toLowerCase()
    if (k === 'name' || k === 'label' || k === 'backend_name' || k === 'display_name') return t('backend_card.field_desc_name')
    if (k === 'url' || k === 'base_url' || k === 'api_base_url' || k === 'api_base' || k === 'endpoint' || k === 'host') return t('backend_card.field_desc_url')
    if (k === 'api_key' || k === 'token' || k === 'api_token' || k === 'secret' || k === 'key') return t('backend_card.field_desc_api_key')
    if (k === 'model' || k === 'model_name' || k === 'model_id') return t('backend_card.field_desc_model')
    if (k === 'enabled' || k === 'enable' || k === 'active') return t('backend_card.field_desc_enabled')
    if (k === 'max_tokens' || k === 'context_length' || k === 'max_context' || k === 'context_window') return t('backend_card.field_desc_max_tokens')
    if (k === 'temperature' || k === 'temp') return t('backend_card.field_desc_temperature')
    if (k === 'system_prompt' || k === 'prompt' || k === 'prompt_template' || k === 'system_message') return t('backend_card.field_desc_system_prompt')
    if (k === 'timeout' || k === 'request_timeout' || k === 'connect_timeout') return t('backend_card.field_desc_timeout')
    return undefined
  }

  const handleSave = () => {
    saveConfigMut.mutate(
      { name: backend.name, config: formValues },
      {
        onSuccess: () => toast(t('backend_card.toast_saved')),
        onError: () => toast(t('backend_card.toast_save_failed'), 'error'),
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
            {backend.configured ? t('backend_card.configured') : t('backend_card.not_configured')}
          </span>
          {backend.supports_glossary && (
            <span
              className="px-1.5 py-0.5 rounded text-[10px] font-medium"
              style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
            >
              {t('backend_card.glossary_badge')}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {successRate !== null && (
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {t('backend_card.success_label', { rate: successRate })}
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
                  {t('backend_card.statistics')}
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
                <span>{t('backend_card.requests_stat', { success: stats.successful_translations, total: stats.total_requests })}</span>
                {stats.avg_response_time_ms > 0 && (
                  <span>{t('backend_card.avg_stat', { ms: Math.round(stats.avg_response_time_ms) })}</span>
                )}
                {stats.last_response_time_ms > 0 && (
                  <span>{t('backend_card.last_stat', { ms: Math.round(stats.last_response_time_ms) })}</span>
                )}
                {stats.total_characters > 0 && (
                  <span>{t('backend_card.chars_stat', { count: stats.total_characters.toLocaleString() })}</span>
                )}
                {stats.consecutive_failures > 0 && (
                  <span style={{ color: 'rgb(245 158 11)' }}>
                    {t('backend_card.consecutive_failures', { count: stats.consecutive_failures })}
                  </span>
                )}
              </div>
              {stats.last_error && (
                <div className="text-xs truncate" style={{ color: 'var(--error)' }} title={stats.last_error}>
                  {t('backend_card.last_error', { error: stats.last_error })}
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
                  description={getFieldDescription(field.key)}
                >
                  <div className="flex items-center gap-1.5 w-full">
                    <input
                      type={field.type === 'password' && !showPasswords[field.key] ? 'password' : field.type === 'number' ? 'number' : 'text'}
                      value={formValues[field.key] === '***configured***' ? '' : (formValues[field.key] ?? field.default ?? '')}
                      onChange={(e) => setFormValues((v) => ({ ...v, [field.key]: e.target.value }))}
                      placeholder={formValues[field.key] === '***configured***' ? t('backend_card.placeholder_configured') : field.default || (field.required ? t('backend_card.placeholder_required') : t('backend_card.placeholder_optional'))}
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
                        title={showPasswords[field.key] ? t('backend_card.hide') : t('backend_card.show')}
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
              {t('backend_card.no_config_required')}
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
              {t('backend_card.test')}
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
                {t('backend_card.save')}
              </button>
            )}

            {/* Test result inline */}
            {testResult && testResult !== 'testing' && (
              <span className="text-xs" style={{ color: testResult.healthy ? 'var(--success)' : 'var(--error)' }}>
                {testResult.healthy ? t('backend_card.healthy_label') : t('backend_card.error_label')}: {testResult.message}
              </span>
            )}
          </div>

          {/* Concurrency slider (Phase A1) */}
          <div className="pt-3" style={{ borderTop: '1px solid var(--border)' }}>
            <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              {t('translation.concurrency.limit')}:{' '}
              <strong>{draftLimit}</strong>
            </label>
            <input
              type="range"
              min={1}
              max={20}
              value={draftLimit}
              onChange={(e) => setDraftLimit(Number(e.target.value))}
              className="w-full"
              aria-label={t('translation.concurrency.limit')}
            />
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {t('translation.concurrency.hint')}
            </div>
          </div>

          {/* Backend info */}
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {t('backend_card.max_batch_size', { count: backend.max_batch_size })}
          </div>
        </div>
      )}
    </div>
  )
}
