import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/components/layout/PageHeader'
import { StatusStripe } from '@/components/dashboard/StatusStripe'
import { MetricsRow } from '@/components/dashboard/MetricsRow'
import { ActivityFeed } from '@/components/dashboard/ActivityFeed'
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar'

export function Dashboard() {
  const { t } = useTranslation('dashboard')

  return (
    <div className="space-y-4">
      <PageHeader title={t('title')} />
      <StatusStripe />
      <MetricsRow />
      <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start', minHeight: '500px' }}>
        <ActivityFeed />
        <DashboardSidebar />
      </div>
    </div>
  )
}
