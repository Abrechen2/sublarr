import { useTranslation } from 'react-i18next'
import { Globe, Store, ShieldAlert, Trash2 } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { useClearProviderCache } from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'
import { ProvidersTab } from './ProvidersTab'
import { MarketplaceTab } from './providers/MarketplaceTab'

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
        <div className="py-4" data-testid="providers-installed-content">
          <ProvidersTab
            values={values}
            onFieldChange={handleFieldChange}
            onSave={handleSave}
          />
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
        <div className="py-4" data-testid="providers-marketplace-content">
          <MarketplaceTab />
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
        <div className="py-4 space-y-3" data-testid="providers-anticaptcha-content">
          <div className="grid grid-cols-[160px_1fr] items-center gap-3">
            <label
              htmlFor="anti-captcha-backend"
              className="text-xs font-medium"
              style={{ color: 'var(--text-secondary)' }}
            >
              {t('settings.providers.anticaptcha.backend', 'Backend')}
            </label>
            <select
              id="anti-captcha-backend"
              value={values['anti_captcha_provider'] ?? ''}
              onChange={(e) => handleFieldChange('anti_captcha_provider', e.target.value)}
              className="px-2 py-1.5 rounded text-xs"
              style={{
                border: '1px solid var(--border)',
                backgroundColor: 'var(--bg-primary)',
                color: 'var(--text-primary)',
              }}
            >
              <option value="">{t('settings.providers.anticaptcha.disabled', 'Disabled')}</option>
              <option value="anticaptcha">Anti-Captcha.com</option>
              <option value="capmonster">CapMonster</option>
            </select>
          </div>
          {values['anti_captcha_provider'] && (
            <div className="grid grid-cols-[160px_1fr] items-center gap-3">
              <label
                htmlFor="anti-captcha-api-key"
                className="text-xs font-medium"
                style={{ color: 'var(--text-secondary)' }}
              >
                {t('settings.providers.anticaptcha.api_key', 'API Key')}
              </label>
              <input
                id="anti-captcha-api-key"
                type="password"
                value={values['anti_captcha_api_key'] ?? ''}
                onChange={(e) => handleFieldChange('anti_captcha_api_key', e.target.value)}
                placeholder={t('settings.providers.anticaptcha.api_key_placeholder', 'Your API key')}
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
    </SettingsDetailLayout>
  )
}
