import { useTranslation } from 'react-i18next'
import { Store, ShieldAlert, Trash2, Settings2, Download } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { FormLayout } from '@/components/settings/layouts'
import type { FormSectionDef } from '@/components/settings/layouts'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { useClearProviderCache } from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'
import { ProvidersCollectionView } from './providers/ProvidersCollectionView'
import { MarketplaceTab } from './providers/MarketplaceTab'
import { strVal, boolVal } from '@/lib/configUtils'
import { settingsInputStyle } from '@/styles/settingsShared'

function parseNum(v: string | undefined, fallback: number): number {
  const n = Number(v)
  return isNaN(n) ? fallback : n
}

const inputStyle: React.CSSProperties = { ...settingsInputStyle, width: '220px', outline: 'none' }

// Settings Template B (FormLayout) wraps the 6 global-provider sections below
// the Template A CollectionView. Order matches scroll order; titleKey resolves
// via useTranslation('settings'). Section count is exactly at the 6-section
// cap — adding a 7th MUST be split into a sub-page (Codex blueprint).
const SECTIONS: readonly FormSectionDef[] = [
  { id: 'global',          titleKey: 'providers_page.global_section' },
  { id: 'marketplace',     titleKey: 'providers_page.marketplace_section' },
  { id: 'anticaptcha',     titleKey: 'providers_page.anticaptcha_section' },
  { id: 'cache',           titleKey: 'providers_page.cache_section' },
  { id: 'download-limits', titleKey: 'providers_page.download_limits_section' },
  { id: 'advanced',        titleKey: 'providers_page.advanced_section', advancedCount: 11 },
]

export function ProvidersSettings() {
  const { t } = useTranslation('settings')
  const { t: ts } = useTranslation('settings')
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()
  const clearCacheMut = useClearProviderCache()

  const values: Record<string, string> = Object.fromEntries(
    Object.entries(configData ?? {}).map(([k, v]) => [k, String(v ?? '')])
  )

  const handleFieldChange = (key: string, value: string) => {
    updateConfig.mutate({ [key]: value })
  }

  const handleSave = (changed: Record<string, unknown>) => {
    updateConfig.mutate(changed)
  }

  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  const handleClearAllCache = () => {
    clearCacheMut.mutate(undefined, {
      onSuccess: () => {
        toast(t('settings.providers.cache_cleared', 'All provider caches cleared'))
      },
      onError: () => {
        toast(t('settings.providers.cache_clear_failed', 'Failed to clear cache'), 'error')
      },
    })
  }

  return (
    <SettingsDetailLayout
      title={t('settings.providers.title', 'Providers')}
      subtitle={t(
        'settings.providers.subtitle',
        'Manage subtitle providers, marketplace plugins, and captcha settings',
      )}
    >
      {/* Provider list — Codex Settings Template A (CollectionLayout) */}
      <div data-testid="providers-installed-content">
        <ProvidersCollectionView
          values={values}
          onFieldChange={handleFieldChange}
          onSave={handleSave}
        />
      </div>

      {/* Global provider settings — Codex Settings Template B (FormLayout)
          wraps the six sections below the CollectionView. Each <section id>
          resolves a TOC anchor in the right rail. */}
      <FormLayout sections={SECTIONS}>

      <section id="global" data-testid="settings.providers.section-global">
      <div data-testid="providers-global-section">
      <SettingsSection
        title={t('settings.providers.global.title', 'Global provider settings')}
        description={t(
          'settings.providers.global.description',
          'Apply across every configured subtitle provider — hidden list, dedup, prioritisation, rate limits, timeouts and cache TTL.',
        )}
        icon={<Settings2 size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-4 space-y-0">
          <FormGroup
            label={ts('providers_page.hidden_providers')}
            hint={ts('providers_page.hidden_providers_hint')}
            htmlFor="providers-hidden"
            data-testid="form-group-providers-hidden"
          >
            <input
              id="providers-hidden"
              type="text"
              data-testid="input-providers-hidden"
              style={inputStyle}
              value={strVal(configData, 'providers_hidden')}
              onChange={(e) => save({ providers_hidden: e.target.value })}
              placeholder="opensubtitles,kitsunekko"
            />
          </FormGroup>

          <FormGroup
            label={ts('providers_page.dedup_on_download')}
            hint={ts('providers_page.dedup_on_download_hint')}
            data-testid="form-group-dedup-on-download"
          >
            <div data-testid="toggle-dedup-on-download">
              <Toggle
                checked={boolVal(configData, 'dedup_on_download')}
                onChange={(v) => save({ dedup_on_download: v })}
              />
            </div>
          </FormGroup>

          <FormGroup
            label={ts('providers_page.auto_prioritize')}
            hint={ts('providers_page.auto_prioritize_hint')}
            data-testid="form-group-provider-auto-prioritize"
          >
            <div data-testid="toggle-provider-auto-prioritize">
              <Toggle
                checked={boolVal(configData, 'provider_auto_prioritize')}
                onChange={(v) => save({ provider_auto_prioritize: v })}
              />
            </div>
          </FormGroup>

          <FormGroup
            label={ts('providers_page.rate_limiting')}
            hint={ts('providers_page.rate_limiting_hint')}
            data-testid="form-group-provider-rate-limit-enabled"
          >
            <div data-testid="toggle-provider-rate-limit-enabled">
              <Toggle
                checked={boolVal(configData, 'provider_rate_limit_enabled')}
                onChange={(v) => save({ provider_rate_limit_enabled: v })}
              />
            </div>
          </FormGroup>

          <FormGroup
            label={ts('providers_page.search_timeout')}
            hint={ts('providers_page.search_timeout_hint')}
            htmlFor="provider-search-timeout"
            data-testid="form-group-provider-search-timeout"
          >
            <input
              id="provider-search-timeout"
              type="number"
              data-testid="input-provider-search-timeout"
              style={{ ...inputStyle, maxWidth: '120px' }}
              value={strVal(configData, 'provider_search_timeout', '30')}
              onChange={(e) => save({ provider_search_timeout: Number(e.target.value) })}
              min={1}
              placeholder="30"
            />
          </FormGroup>

          <FormGroup
            label={ts('providers_page.cache_ttl')}
            hint={ts('providers_page.cache_ttl_hint')}
            htmlFor="provider-cache-ttl-minutes"
            data-testid="form-group-provider-cache-ttl-minutes"
          >
            <input
              id="provider-cache-ttl-minutes"
              type="number"
              data-testid="input-provider-cache-ttl-minutes"
              style={{ ...inputStyle, maxWidth: '120px' }}
              value={strVal(configData, 'provider_cache_ttl_minutes', '60')}
              onChange={(e) => save({ provider_cache_ttl_minutes: Number(e.target.value) })}
              min={0}
              placeholder="60"
            />
          </FormGroup>

          <FormGroup
            label={ts('providers_page.auto_disable_cooldown')}
            hint={ts('providers_page.auto_disable_cooldown_hint')}
            htmlFor="provider-auto-disable-cooldown-minutes"
            data-testid="form-group-provider-auto-disable-cooldown-minutes"
          >
            <input
              id="provider-auto-disable-cooldown-minutes"
              type="number"
              data-testid="input-provider-auto-disable-cooldown-minutes"
              style={{ ...inputStyle, maxWidth: '120px' }}
              value={strVal(configData, 'provider_auto_disable_cooldown_minutes', '30')}
              onChange={(e) =>
                save({ provider_auto_disable_cooldown_minutes: Number(e.target.value) })
              }
              min={0}
              placeholder="30"
            />
          </FormGroup>
        </div>
      </SettingsSection>
      </div>
      </section>

      {/* Marketplace */}
      <section id="marketplace" data-testid="settings.providers.section-marketplace">
      <SettingsSection
        data-testid="providers-marketplace-section"
        title={t('settings.providers.marketplace.title', 'Marketplace')}
        description={t(
          'settings.providers.marketplace.description',
          'Browse and install community and official subtitle provider plugins.',
        )}
        icon={<Store size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-4 space-y-0" data-testid="providers-marketplace-content">
          <MarketplaceTab />

          <div className="mt-6 space-y-0">
            <FormGroup
              label={ts('providers_page.github_token')}
              hint={ts('providers_page.github_token_hint')}
              htmlFor="github-token"
              data-testid="form-group-github-token"
            >
              <input
                id="github-token"
                type="password"
                data-testid="input-github-token"
                style={inputStyle}
                value={strVal(configData, 'github_token')}
                onChange={(e) => save({ github_token: e.target.value })}
                placeholder="ghp_..."
                autoComplete="off"
              />
            </FormGroup>

            <FormGroup
              label={ts('providers_page.plugins_directory')}
              hint={ts('providers_page.plugins_directory_hint')}
              htmlFor="plugins-dir"
              data-testid="form-group-plugins-dir"
            >
              <input
                id="plugins-dir"
                type="text"
                data-testid="input-plugins-dir"
                style={inputStyle}
                value={strVal(configData, 'plugins_dir')}
                onChange={(e) => save({ plugins_dir: e.target.value })}
                placeholder="/config/plugins"
              />
            </FormGroup>

            <FormGroup
              label={ts('providers_page.hot_reload_plugins')}
              hint={ts('providers_page.hot_reload_plugins_hint')}
              data-testid="form-group-plugin-hot-reload"
            >
              <div data-testid="toggle-plugin-hot-reload">
                <Toggle
                  checked={boolVal(configData, 'plugin_hot_reload')}
                  onChange={(v) => save({ plugin_hot_reload: v })}
                />
              </div>
            </FormGroup>
          </div>
        </div>
      </SettingsSection>
      </section>

      {/* Anti-Captcha Config */}
      <section id="anticaptcha" data-testid="settings.providers.section-anticaptcha">
      <SettingsSection
        data-testid="providers-anticaptcha-section"
        title={t('settings.providers.anticaptcha.title', 'Anti-Captcha')}
        description={t(
          'settings.providers.anticaptcha.description',
          'Automatically solve captcha challenges from providers like Kitsunekko. Supports Anti-Captcha.com and CapMonster.',
        )}
        icon={<ShieldAlert size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-4 space-y-0" data-testid="providers-anticaptcha-content">
          <FormGroup
            label={ts('providers_page.backend')}
            hint={ts('providers_page.backend_hint')}
            htmlFor="anti-captcha-backend"
            data-testid="form-group-anti-captcha-backend"
          >
            <select
              id="anti-captcha-backend"
              value={strVal(configData, 'anti_captcha_provider')}
              onChange={(e) => save({ anti_captcha_provider: e.target.value })}
              style={{
                ...inputStyle,
                width: '220px',
              }}
            >
              <option value="">{t('settings.providers.anticaptcha.disabled', 'Disabled')}</option>
              <option value="anticaptcha">Anti-Captcha.com</option>
              <option value="capmonster">CapMonster</option>
            </select>
          </FormGroup>

          {strVal(configData, 'anti_captcha_provider') && (
            <FormGroup
              label={ts('providers_page.api_key')}
              hint={ts('providers_page.api_key_hint')}
              htmlFor="anti-captcha-api-key"
              data-testid="form-group-anti-captcha-api-key"
            >
              <input
                id="anti-captcha-api-key"
                type="password"
                data-testid="input-anti-captcha-api-key"
                style={inputStyle}
                value={strVal(configData, 'anti_captcha_api_key')}
                onChange={(e) => save({ anti_captcha_api_key: e.target.value })}
                placeholder={t('settings.providers.anticaptcha.api_key_placeholder', 'Your API key')}
                autoComplete="off"
              />
            </FormGroup>
          )}
        </div>
      </SettingsSection>
      </section>

      {/* Cache Management */}
      <section id="cache" data-testid="settings.providers.section-cache">
      <SettingsSection
        data-testid="providers-cache-section"
        title={t('settings.providers.cache.title', 'Cache Management')}
        description={t(
          'settings.providers.cache.description',
          'Clear cached subtitle search results. Individual provider caches can be cleared from the provider card.',
        )}
        icon={<Trash2 size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-4" data-testid="providers-cache-content">
          <button
            onClick={handleClearAllCache}
            disabled={clearCacheMut.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150 hover:opacity-80 disabled:opacity-50"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
            }}
            data-testid="clear-all-cache-btn"
          >
            <Trash2 size={12} />
            {t('settings.providers.cache.clear_all', 'Clear All Provider Caches')}
          </button>
        </div>
      </SettingsSection>
      </section>

      {/* Download Limits (Step 44) */}
      <section id="download-limits" data-testid="settings.providers.section-download-limits">
      <div data-testid="section-download-limits">
        <SettingsSection
          title={t('settings.providers.downloadLimits.title', 'Download Limits')}
          description={t(
            'settings.providers.downloadLimits.description',
            'Concurrency and size limits for subtitle provider downloads.',
          )}
          icon={<Download size={16} style={{ color: 'var(--accent)' }} />}
        >
          <div className="py-4 space-y-0" data-testid="download-limits-content">
            <FormGroup
              label={ts('providers_page.concurrent_searches')}
              hint={ts('providers_page.concurrent_searches_hint')}
              htmlFor="max-concurrent-provider-searches"
              data-testid="form-group-max-concurrent-provider-searches"
            >
              <input
                id="max-concurrent-provider-searches"
                type="number"
                data-testid="input-max-concurrent-provider-searches"
                style={{ ...inputStyle, maxWidth: '100px' }}
                value={parseNum(values['max_concurrent_provider_searches'], 3)}
                onChange={(e) =>
                  handleFieldChange(
                    'max_concurrent_provider_searches',
                    String(Number(e.target.value)),
                  )
                }
                min={1}
                max={10}
              />
            </FormGroup>

            <FormGroup
              label={ts('providers_page.max_subtitle_size')}
              hint={ts('providers_page.max_subtitle_size_hint')}
              htmlFor="max-subtitle-file-size-kb"
              data-testid="form-group-max-subtitle-file-size-kb"
            >
              <input
                id="max-subtitle-file-size-kb"
                type="number"
                data-testid="input-max-subtitle-file-size-kb"
                style={{ ...inputStyle, maxWidth: '120px' }}
                value={parseNum(values['max_subtitle_file_size_kb'], 2048)}
                onChange={(e) =>
                  handleFieldChange(
                    'max_subtitle_file_size_kb',
                    String(Number(e.target.value)),
                  )
                }
                min={100}
                max={10240}
              />
            </FormGroup>

            <FormGroup
              label={ts('providers_page.provider_delay')}
              hint={ts('providers_page.provider_delay_hint')}
              htmlFor="download-delay-between-providers-ms"
              data-testid="form-group-download-delay-between-providers-ms"
            >
              <input
                id="download-delay-between-providers-ms"
                type="number"
                data-testid="input-download-delay-between-providers-ms"
                style={{ ...inputStyle, maxWidth: '120px' }}
                value={parseNum(values['download_delay_between_providers_ms'], 0)}
                onChange={(e) =>
                  handleFieldChange(
                    'download_delay_between_providers_ms',
                    String(Number(e.target.value)),
                  )
                }
                min={0}
                max={5000}
              />
            </FormGroup>
          </div>
        </SettingsSection>
      </div>
      </section>

      {/* Advanced — Provider Engine */}
      <section id="advanced" data-testid="settings.providers.section-advanced">
      <div data-testid="providers-advanced-section">
        <SettingsSection
          title={t('settings.providers.advanced.title', 'Provider Engine')}
          description={t(
            'settings.providers.advanced.description',
            'Fine-tune provider reranking, dynamic timeouts, and the circuit breaker.',
          )}
          icon={<Settings2 size={16} style={{ color: 'var(--accent)' }} />}
          advanced={
            <>
              {/* Reranking */}
              <FormGroup
                label={ts('providers_page.provider_reranking')}
                hint={ts('providers_page.provider_reranking_hint')}
                htmlFor="provider-reranking-enabled"
                data-testid="form-group-provider-reranking-enabled"
              >
                <div data-testid="toggle-provider-reranking-enabled">
                  <Toggle
                    checked={boolVal(configData, 'provider_reranking_enabled')}
                    onChange={(v) => save({ provider_reranking_enabled: v })}
                  />
                </div>
              </FormGroup>

              <FormGroup
                label={ts('providers_page.reranking_min_downloads')}
                hint={ts('providers_page.reranking_min_downloads_hint')}
                htmlFor="provider-reranking-min-downloads"
                data-testid="form-group-provider-reranking-min-downloads"
              >
                <input
                  id="provider-reranking-min-downloads"
                  type="number"
                  data-testid="input-provider-reranking-min-downloads"
                  style={{ ...inputStyle, maxWidth: '120px' }}
                  value={strVal(configData, 'provider_reranking_min_downloads', '10')}
                  onChange={(e) =>
                    save({ provider_reranking_min_downloads: Number(e.target.value) })
                  }
                  min={0}
                  placeholder="10"
                />
              </FormGroup>

              <FormGroup
                label={ts('providers_page.reranking_max_modifier')}
                hint={ts('providers_page.reranking_max_modifier_hint')}
                htmlFor="provider-reranking-max-modifier"
                data-testid="form-group-provider-reranking-max-modifier"
              >
                <input
                  id="provider-reranking-max-modifier"
                  type="number"
                  data-testid="input-provider-reranking-max-modifier"
                  style={{ ...inputStyle, maxWidth: '120px' }}
                  value={strVal(configData, 'provider_reranking_max_modifier', '0.3')}
                  onChange={(e) =>
                    save({ provider_reranking_max_modifier: Number(e.target.value) })
                  }
                  min={0}
                  step={0.05}
                  placeholder="0.3"
                />
              </FormGroup>

              {/* Dynamic Timeouts */}
              <FormGroup
                label={ts('providers_page.dynamic_timeouts')}
                hint={ts('providers_page.dynamic_timeouts_hint')}
                data-testid="form-group-provider-dynamic-timeout-enabled"
              >
                <div data-testid="toggle-provider-dynamic-timeout-enabled">
                  <Toggle
                    checked={boolVal(configData, 'provider_dynamic_timeout_enabled')}
                    onChange={(v) => save({ provider_dynamic_timeout_enabled: v })}
                  />
                </div>
              </FormGroup>

              <FormGroup
                label={ts('providers_page.dyn_timeout_min_samples')}
                hint={ts('providers_page.dyn_timeout_min_samples_hint')}
                htmlFor="provider-dynamic-timeout-min-samples"
                data-testid="form-group-provider-dynamic-timeout-min-samples"
              >
                <input
                  id="provider-dynamic-timeout-min-samples"
                  type="number"
                  data-testid="input-provider-dynamic-timeout-min-samples"
                  style={{ ...inputStyle, maxWidth: '120px' }}
                  value={strVal(configData, 'provider_dynamic_timeout_min_samples', '5')}
                  onChange={(e) =>
                    save({ provider_dynamic_timeout_min_samples: Number(e.target.value) })
                  }
                  min={1}
                  placeholder="5"
                />
              </FormGroup>

              <FormGroup
                label={ts('providers_page.dyn_timeout_multiplier')}
                hint={ts('providers_page.dyn_timeout_multiplier_hint')}
                htmlFor="provider-dynamic-timeout-multiplier"
                data-testid="form-group-provider-dynamic-timeout-multiplier"
              >
                <input
                  id="provider-dynamic-timeout-multiplier"
                  type="number"
                  data-testid="input-provider-dynamic-timeout-multiplier"
                  style={{ ...inputStyle, maxWidth: '120px' }}
                  value={strVal(configData, 'provider_dynamic_timeout_multiplier', '1.5')}
                  onChange={(e) =>
                    save({ provider_dynamic_timeout_multiplier: Number(e.target.value) })
                  }
                  min={1}
                  step={0.1}
                  placeholder="1.5"
                />
              </FormGroup>

              <FormGroup
                label={ts('providers_page.dyn_timeout_buffer')}
                hint={ts('providers_page.dyn_timeout_buffer_hint')}
                htmlFor="provider-dynamic-timeout-buffer-secs"
                data-testid="form-group-provider-dynamic-timeout-buffer-secs"
              >
                <input
                  id="provider-dynamic-timeout-buffer-secs"
                  type="number"
                  data-testid="input-provider-dynamic-timeout-buffer-secs"
                  style={{ ...inputStyle, maxWidth: '120px' }}
                  value={strVal(configData, 'provider_dynamic_timeout_buffer_secs', '2')}
                  onChange={(e) =>
                    save({ provider_dynamic_timeout_buffer_secs: Number(e.target.value) })
                  }
                  min={0}
                  placeholder="2"
                />
              </FormGroup>

              <FormGroup
                label={ts('providers_page.dyn_timeout_min')}
                hint={ts('providers_page.dyn_timeout_min_hint')}
                htmlFor="provider-dynamic-timeout-min-secs"
                data-testid="form-group-provider-dynamic-timeout-min-secs"
              >
                <input
                  id="provider-dynamic-timeout-min-secs"
                  type="number"
                  data-testid="input-provider-dynamic-timeout-min-secs"
                  style={{ ...inputStyle, maxWidth: '120px' }}
                  value={strVal(configData, 'provider_dynamic_timeout_min_secs', '5')}
                  onChange={(e) =>
                    save({ provider_dynamic_timeout_min_secs: Number(e.target.value) })
                  }
                  min={1}
                  placeholder="5"
                />
              </FormGroup>

              <FormGroup
                label={ts('providers_page.dyn_timeout_max')}
                hint={ts('providers_page.dyn_timeout_max_hint')}
                htmlFor="provider-dynamic-timeout-max-secs"
                data-testid="form-group-provider-dynamic-timeout-max-secs"
              >
                <input
                  id="provider-dynamic-timeout-max-secs"
                  type="number"
                  data-testid="input-provider-dynamic-timeout-max-secs"
                  style={{ ...inputStyle, maxWidth: '120px' }}
                  value={strVal(configData, 'provider_dynamic_timeout_max_secs', '60')}
                  onChange={(e) =>
                    save({ provider_dynamic_timeout_max_secs: Number(e.target.value) })
                  }
                  min={1}
                  placeholder="60"
                />
              </FormGroup>

              {/* Circuit Breaker */}
              <FormGroup
                label={ts('providers_page.circuit_breaker_threshold')}
                hint={ts('providers_page.circuit_breaker_threshold_hint')}
                htmlFor="circuit-breaker-failure-threshold"
                data-testid="form-group-circuit-breaker-failure-threshold"
              >
                <input
                  id="circuit-breaker-failure-threshold"
                  type="number"
                  data-testid="input-circuit-breaker-failure-threshold"
                  style={{ ...inputStyle, maxWidth: '120px' }}
                  value={strVal(configData, 'circuit_breaker_failure_threshold', '5')}
                  onChange={(e) =>
                    save({ circuit_breaker_failure_threshold: Number(e.target.value) })
                  }
                  min={1}
                  placeholder="5"
                />
              </FormGroup>

              <FormGroup
                label={ts('providers_page.circuit_breaker_cooldown')}
                hint={ts('providers_page.circuit_breaker_cooldown_hint')}
                htmlFor="circuit-breaker-cooldown-seconds"
                data-testid="form-group-circuit-breaker-cooldown-seconds"
              >
                <input
                  id="circuit-breaker-cooldown-seconds"
                  type="number"
                  data-testid="input-circuit-breaker-cooldown-seconds"
                  style={{ ...inputStyle, maxWidth: '120px' }}
                  value={strVal(configData, 'circuit_breaker_cooldown_seconds', '300')}
                  onChange={(e) =>
                    save({ circuit_breaker_cooldown_seconds: Number(e.target.value) })
                  }
                  min={10}
                  placeholder="300"
                />
              </FormGroup>
            </>
          }
        >
          {/* No primary content — all fields are in the collapsible advanced area */}
          <span />
        </SettingsSection>
      </div>
      </section>

      </FormLayout>
    </SettingsDetailLayout>
  )
}
