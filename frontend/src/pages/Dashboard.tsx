/**
 * Dashboard page — automation-first redesign.
 *
 * Layout: AutomationBanner → HeroStats → NeedsAttentionCard → Widget Grid
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Settings2, Info } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { AutomationBanner } from '@/components/dashboard/AutomationBanner'
import { HeroStats } from '@/components/dashboard/HeroStats'
import { NeedsAttentionCard } from '@/components/dashboard/NeedsAttentionCard'
import { DashboardGrid } from '@/components/dashboard/DashboardGrid'
import { WidgetSettingsModal } from '@/components/dashboard/WidgetSettingsModal'
import { useUpdateInfo } from '@/hooks/useSystemApi'

export function Dashboard() {
  const { t } = useTranslation('dashboard')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const { data: updateInfo } = useUpdateInfo()

  return (
    <div className="space-y-5">
      <PageHeader
        title={t('title')}
        actions={
          <button
            data-testid="customize-widgets-btn"
            onClick={() => setSettingsOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 hover:opacity-80"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
            }}
          >
            <Settings2 size={14} />
            {t('widgets.customize')}
          </button>
        }
      />

      {/* Update check banner */}
      {updateInfo?.update_available && (
        <div
          className="flex items-center gap-3 rounded-lg px-4 py-3 text-sm"
          style={{ backgroundColor: 'var(--accent-muted, color-mix(in srgb, var(--accent) 10%, transparent))', border: '1px solid var(--accent)', color: 'var(--text)' }}
          data-testid="update-banner"
        >
          <Info size={16} style={{ color: 'var(--accent)', flexShrink: 0 }} />
          <span>
            Update available: <strong>{updateInfo.latest_version}</strong>
          </span>
          <a
            href={updateInfo.release_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto underline"
            style={{ color: 'var(--accent)' }}
          >
            View release
          </a>
        </div>
      )}

      <AutomationBanner />
      <HeroStats />
      <NeedsAttentionCard />

      <DashboardGrid onOpenSettings={() => setSettingsOpen(true)} />

      <WidgetSettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  )
}
