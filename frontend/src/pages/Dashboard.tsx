/**
 * Dashboard page — automation-first redesign.
 *
 * Layout: AutomationBanner → HeroStats → NeedsAttentionCard → Widget Grid
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Settings2 } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { AutomationBanner } from '@/components/dashboard/AutomationBanner'
import { HeroStats } from '@/components/dashboard/HeroStats'
import { NeedsAttentionCard } from '@/components/dashboard/NeedsAttentionCard'
import { DashboardGrid } from '@/components/dashboard/DashboardGrid'
import { WidgetSettingsModal } from '@/components/dashboard/WidgetSettingsModal'

export function Dashboard() {
  const { t } = useTranslation('dashboard')
  const [settingsOpen, setSettingsOpen] = useState(false)

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
