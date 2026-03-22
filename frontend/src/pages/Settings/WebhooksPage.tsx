import { Copy, Webhook } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { SettingRow } from '@/components/shared/SettingRow'
import { toast } from '@/components/shared/Toast'

// ─── WebhooksPage ──────────────────────────────────────────────────────────────

const WEBHOOKS = [
  {
    service: 'Sonarr',
    path: '/api/v1/webhook/sonarr',
    description: 'Paste into Sonarr → Settings → Connect → Webhook',
  },
  {
    service: 'Radarr',
    path: '/api/v1/webhook/radarr',
    description: 'Paste into Radarr → Settings → Connect → Webhook',
  },
  {
    service: 'Jellyfin',
    path: '/api/v1/webhook/jellyfin',
    description: 'Paste into Jellyfin → Dashboard → Webhooks plugin',
  },
] as const

export function WebhooksPage() {
  const baseUrl = window.location.origin

  return (
    <SettingsDetailLayout
        title="Incoming Webhooks"
        subtitle="Copy these URLs into your media server webhook settings."
      >
        <div className="space-y-4">
          {WEBHOOKS.map((w) => {
            const fullUrl = `${baseUrl}${w.path}`
            return (
              <SettingsSection
                key={w.service}
                title={w.service}
                description={w.description}
                icon={<Webhook size={16} style={{ color: 'var(--accent)' }} />}
              >
                <SettingRow label="Webhook URL">
                  <div
                    className="flex items-center gap-2"
                    style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-muted)' }}
                  >
                    <span data-testid={`webhook-url-${w.service.toLowerCase()}`}>{fullUrl}</span>
                    <button
                      onClick={() => {
                        void navigator.clipboard.writeText(fullUrl)
                        toast('Copied!')
                      }}
                      className="p-1 rounded transition-colors hover:opacity-80"
                      title="Copy URL"
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
