import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/components/layout/PageHeader'
import { StatusStripe } from '@/components/dashboard/StatusStripe'
import { MetricsRow } from '@/components/dashboard/MetricsRow'
import { ActivityFeed } from '@/components/dashboard/ActivityFeed'
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar'
import { BudgetWidget } from '@/components/dashboard/BudgetWidget'

export function Dashboard() {
  const { t } = useTranslation('dashboard')

  return (
    <div className="space-y-4">
      <PageHeader title={t('title')} />
      <StatusStripe />
      <MetricsRow />
      {/* Stacks on phones; two columns from md up */}
      <div className="flex flex-col md:flex-row gap-4 items-stretch md:items-start md:min-h-[500px]">
        <ActivityFeed />
        <DashboardSidebar />
      </div>
      <BudgetWidget />
    </div>
  )
}
