/**
 * QualityWidget -- Thin wrapper around the existing HealthDashboardWidget.
 *
 * Imports and renders the existing health quality sparkline component
 * within a Suspense boundary.
 */
import { lazy, Suspense } from 'react'

const HealthDashboardWidget = lazy(() =>
  import('@/components/health/HealthDashboardWidget').then((m) => ({
    default: m.HealthDashboardWidget,
  }))
)

function SkeletonPlaceholder() {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="skeleton w-full h-24 rounded" />
    </div>
  )
}

export default function QualityWidget() {
  return (
    <Suspense fallback={<SkeletonPlaceholder />}>
      <HealthDashboardWidget />
    </Suspense>
  )
}
