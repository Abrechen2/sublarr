/**
 * Dashboard page -- renders the customizable widget grid.
 *
 * All section logic has been extracted into individual widget components
 * under components/dashboard/widgets/. This page manages only the grid
 * container, settings modal state, and the customize button.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Settings2 } from 'lucide-react'
import { DashboardGrid } from '@/components/dashboard/DashboardGrid'
import { WidgetSettingsModal } from '@/components/dashboard/WidgetSettingsModal'

export function Dashboard() {
  const { t } = useTranslation('dashboard')
  const [settingsOpen, setSettingsOpen] = useState(false)

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1>{t('title')}</h1>
        <button
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
      </div>

      <DashboardGrid onOpenSettings={() => setSettingsOpen(true)} />

      <WidgetSettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  )
}
