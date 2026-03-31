import { useTranslation } from 'react-i18next'
import { Globe, Store, ShieldAlert, Trash2, Settings2, Download } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { useClearProviderCache } from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'
import { ProvidersTab } from './ProvidersTab'
import { MarketplaceTab } from './providers/MarketplaceTab'
import { strVal, boolVal } from '@/lib/configUtils'
import { settingsInputStyle } from '@/styles/settingsShared'

function parseNum(v: string | undefined, fallback: number): number {
  const n = Number(v)
  return isNaN(n) ? fallback : n
}

const inputStyle: React.CSSProperties = { ...settingsInputStyle, width: '220px', outline: 'none' }

export function ProvidersSettings() {
  const { t } = useTranslation('common')
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
      {/* Installed Providers */}
      <SettingsSection
        data-testid="providers-installed-section"
        title={t('settings.providers.installed.title', 'Installed Providers')}
        description={t(
          'settings.providers.installed.description',
          'Configure and prioritise active subtitle providers. Drag to reorder.',
        )}
        icon={<Globe size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-4 space-y-0" data-testid="providers-installed-content">
          <ProvidersTab
            values={values}
            onFieldChange={handleFieldChange}
            onSave={handleSave}
          />

          <div className="mt-6 space-y-0">
            <FormGroup
              label="Hidden Providers"
              hint="Comma-separated provider IDs to hide from the grid (e.g. opensubtitles,kitsunekko)."
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
              label="Deduplicate on Download"
              hint="Skip downloading a subtitle if an identical file is already present."
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
              label="Auto-Prioritize Providers"
              hint="Automatically sort providers by recent success rate."
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
              label="Rate Limiting"
              hint="Enforce per-provider request rate limits to avoid bans."
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
              label="Search Timeout (s)"
              hint="Seconds before a provider search request times out."
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
              label="Cache TTL (minutes)"
              hint="How long to cache provider search results before expiring."
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
              label="Auto-Disable Cooldown (min)"
              hint="Minutes a provider stays disabled after repeated failures."
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
        </div>
      </SettingsSection>

      {/* Marketplace */}
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
              label="GitHub Token"
              hint="Personal access token for higher Marketplace API rate limits."
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
              label="Plugins Directory"
              hint="Path where plugin files are stored. Leave empty to use the default."
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
              label="Hot Reload Plugins"
              hint="Automatically reload plugins when their files change on disk."
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

      {/* Anti-Captcha Config */}
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
            label="Backend"
            hint="Select the anti-captcha service provider."
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
              label="API Key"
              hint="Your anti-captcha service API key."
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

      {/* Cache Management */}
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

      {/* Download Limits (Step 44) */}
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
              label="Concurrent Provider Searches"
              hint="Maximum number of providers searched simultaneously"
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
              label="Max Subtitle File Size (KB)"
              hint="Reject subtitle files larger than this size"
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
              label="Delay Between Providers (ms)"
              hint="Milliseconds to wait between each provider request"
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

      {/* Advanced — Provider Engine */}
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
                label="Provider Reranking"
                hint="Reorder provider results based on historical download success rates."
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
                label="Reranking Min Downloads"
                hint="Minimum download count before a provider is eligible for reranking."
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
                label="Reranking Max Modifier"
                hint="Maximum score modifier applied by reranking (e.g. 0.3 = ±30%)."
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
                label="Dynamic Timeouts"
                hint="Automatically adjust search timeouts based on provider response history."
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
                label="Dynamic Timeout Min Samples"
                hint="Minimum number of response samples before dynamic adjustment kicks in."
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
                label="Dynamic Timeout Multiplier"
                hint="Multiply the measured average response time by this factor for the timeout."
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
                label="Dynamic Timeout Buffer (s)"
                hint="Fixed seconds added on top of the calculated dynamic timeout."
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
                label="Dynamic Timeout Min (s)"
                hint="Minimum timeout regardless of dynamic calculation."
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
                label="Dynamic Timeout Max (s)"
                hint="Maximum timeout cap even if dynamic calculation exceeds it."
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
                label="Circuit Breaker Threshold"
                hint="Number of consecutive failures before a provider is temporarily disabled."
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
                label="Circuit Breaker Cooldown (s)"
                hint="Seconds a provider stays in OPEN state before being retried."
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
    </SettingsDetailLayout>
  )
}
