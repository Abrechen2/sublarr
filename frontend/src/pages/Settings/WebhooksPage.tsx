import { Copy, Webhook } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { SettingRow } from '@/components/shared/SettingRow'
import { toast } from '@/components/shared/Toast'

// ─── WebhooksPage ──────────────────────────────────────────────────────────────

const WEBHOOKS = [
  { service: 'Sonarr', path: '/api/v1/webhook/sonarr', descKey: 'webhooks_page.sonarr_desc' },
  { service: 'Radarr', path: '/api/v1/webhook/radarr', descKey: 'webhooks_page.radarr_desc' },
  { service: 'Jellyfin', path: '/api/v1/webhook/jellyfin', descKey: 'webhooks_page.jellyfin_desc' },
] as const

export function WebhooksPage() {
  const { t } = useTranslation('settings')
  const baseUrl = window.location.origin

  return (
    <SettingsDetailLayout
        title={t('webhooks_page.title')}
        subtitle={t('webhooks_page.subtitle')}
      >
        <div className="space-y-4">
          {WEBHOOKS.map((w) => {
            const fullUrl = `${baseUrl}${w.path}`
            return (
              <SettingsSection
                key={w.service}
                title={w.service}
                description={t(w.descKey)}
                icon={<Webhook size={16} style={{ color: 'var(--accent)' }} />}
              >
                <SettingRow label={t('webhooks_page.webhook_url_label')}>
                  <div
                    className="flex items-center gap-2"
                    style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-muted)' }}
                  >
                    <span data-testid={`webhook-url-${w.service.toLowerCase()}`}>{fullUrl}</span>
                    <button
                      onClick={() => {
                        if (navigator.clipboard) {
                          void navigator.clipboard.writeText(fullUrl)
                        } else {
                          const el = document.createElement('textarea')
                          el.value = fullUrl
                          document.body.appendChild(el)
                          el.select()
                          document.execCommand('copy')
                          document.body.removeChild(el)
                        }
                        toast(t('webhooks_page.copied'))
                      }}
                      className="p-1 rounded transition-colors hover:opacity-80"
                      title={t('webhooks_page.copy_url_title')}
                      style={{ color: 'var(--text-secondary)', flexShrink: 0 }}
                      data-testid={`webhook-copy-${w.service.toLowerCase()}`}
                    >
                      <Copy size={14} />
                    </button>
                  </div>
                </SettingRow>
              </SettingsSection>
            )
          })}
        </div>
      </SettingsDetailLayout>
  )
}
