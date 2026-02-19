/**
 * Widget definition registry.
 *
 * Central registry of all dashboard widget types with metadata (id, title key,
 * icon, default layout, lazy-loaded component). The grid uses widget IDs to
 * reference layouts and the registry to resolve components.
 */
import { lazy } from 'react'
import type { ComponentType, LazyExoticComponent } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  BarChart3,
  Zap,
  Server,
  Shield,
  ShieldCheck,
  Languages,
  AlertCircle,
  Activity,
} from 'lucide-react'
import type { LayoutItem } from 'react-grid-layout'

export interface WidgetDefinition {
  readonly id: string
  readonly titleKey: string
  readonly icon: LucideIcon
  readonly defaultLayout: {
    w: number
    h: number
    minW?: number
    minH?: number
    x: number
    y: number
  }
  readonly component: LazyExoticComponent<ComponentType>
}

export const WIDGET_REGISTRY: readonly WidgetDefinition[] = [
  {
    id: 'stat-cards',
    titleKey: 'widgets.stat_cards',
    icon: BarChart3,
    defaultLayout: { w: 12, h: 2, x: 0, y: 0, minW: 6, minH: 2 },
    component: lazy(() => import('./widgets/StatCardsWidget')),
  },
  {
    id: 'quick-actions',
    titleKey: 'widgets.quick_actions',
    icon: Zap,
    defaultLayout: { w: 12, h: 2, x: 0, y: 2, minW: 4, minH: 2 },
    component: lazy(() => import('./widgets/QuickActionsWidget')),
  },
  {
    id: 'service-status',
    titleKey: 'widgets.service_status',
    icon: Server,
    defaultLayout: { w: 6, h: 3, x: 0, y: 4, minW: 4, minH: 2 },
    component: lazy(() => import('./widgets/ServiceStatusWidget')),
  },
  {
    id: 'provider-health',
    titleKey: 'widgets.provider_health',
    icon: Shield,
    defaultLayout: { w: 6, h: 3, x: 6, y: 4, minW: 4, minH: 2 },
    component: lazy(() => import('./widgets/ProviderHealthWidget')),
  },
  {
    id: 'quality',
    titleKey: 'widgets.quality',
    icon: ShieldCheck,
    defaultLayout: { w: 12, h: 3, x: 0, y: 7, minW: 6, minH: 3 },
    component: lazy(() => import('./widgets/QualityWidget')),
  },
  {
    id: 'translation-stats',
    titleKey: 'widgets.translation_stats',
    icon: Languages,
    defaultLayout: { w: 4, h: 3, x: 0, y: 10, minW: 3, minH: 2 },
    component: lazy(() => import('./widgets/TranslationStatsWidget')),
  },
  {
    id: 'wanted-summary',
    titleKey: 'widgets.wanted_summary',
    icon: AlertCircle,
    defaultLayout: { w: 4, h: 3, x: 4, y: 10, minW: 3, minH: 2 },
    component: lazy(() => import('./widgets/WantedSummaryWidget')),
  },
  {
    id: 'recent-activity',
    titleKey: 'widgets.recent_activity',
    icon: Activity,
    defaultLayout: { w: 4, h: 4, x: 8, y: 10, minW: 4, minH: 3 },
    component: lazy(() => import('./widgets/RecentActivityWidget')),
  },
] as const

/** Widget ID type derived from registry */
export type WidgetId = (typeof WIDGET_REGISTRY)[number]['id']

/**
 * Generate default layouts from the widget registry.
 * Each item's `i` field is set to the widget ID for react-grid-layout.
 */
export function getDefaultLayouts(): LayoutItem[] {
  return WIDGET_REGISTRY.map((widget) => ({
    i: widget.id,
    x: widget.defaultLayout.x,
    y: widget.defaultLayout.y,
    w: widget.defaultLayout.w,
    h: widget.defaultLayout.h,
    minW: widget.defaultLayout.minW,
    minH: widget.defaultLayout.minH,
  }))
}
