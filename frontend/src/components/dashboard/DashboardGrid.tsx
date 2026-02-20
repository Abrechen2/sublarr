/**
 * Responsive drag-and-drop dashboard grid.
 *
 * Uses react-grid-layout v2 ResponsiveGridLayout with useContainerWidth
 * for responsive breakpoints. Layout is persisted via useDashboardStore.
 *
 * Pitfall handling:
 * - Pitfall 4: mounted guard prevents layout flash before hydration
 * - Pitfall 5: onLayoutChange used for all-layouts persistence (not per-pixel)
 */
import { Suspense, useMemo, useCallback } from 'react'
import { ResponsiveGridLayout, useContainerWidth } from 'react-grid-layout'
import type { Layout, LayoutItem, ResponsiveLayouts } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import { useTranslation } from 'react-i18next'
import { Settings2 } from 'lucide-react'
import { useDashboardStore } from '@/stores/dashboardStore'
import { WIDGET_REGISTRY, getDefaultLayouts } from './widgetRegistry'
import { WidgetWrapper } from './WidgetWrapper'

const BREAKPOINTS = { lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }
const COLS = { lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 }
const NO_PADDING_WIDGETS = new Set(['stat-cards'])

/** Skeleton placeholder for lazy-loaded widgets */
export function WidgetSkeleton() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="skeleton w-12 h-12 rounded-lg" />
    </div>
  )
}

interface DashboardGridProps {
  onOpenSettings: () => void
}

export function DashboardGrid({ onOpenSettings }: DashboardGridProps) {
  const { t } = useTranslation('dashboard')
  const { width, mounted, containerRef } = useContainerWidth({
    initialWidth: 1280,
  })

  const storedLayouts = useDashboardStore((s) => s.layouts)
  const hiddenWidgets = useDashboardStore((s) => s.hiddenWidgets)
  const setLayouts = useDashboardStore((s) => s.setLayouts)
  const toggleWidget = useDashboardStore((s) => s.toggleWidget)

  // Filter visible widgets
  const visibleWidgets = useMemo(
    () => WIDGET_REGISTRY.filter((w) => !hiddenWidgets.includes(w.id)),
    [hiddenWidgets]
  )

  // Merge stored layouts with defaults for all breakpoints
  const mergedLayouts = useMemo(() => {
    const defaults = getDefaultLayouts()
    const result: Record<string, LayoutItem[]> = {}
    for (const bp of Object.keys(BREAKPOINTS)) {
      const stored = storedLayouts[bp]
      if (stored && stored.length > 0) {
        // Only include layouts for visible widgets, add defaults for new ones
        const visibleIds = new Set(visibleWidgets.map((w) => w.id))
        const filtered = stored.filter((item) => visibleIds.has(item.i))
        const missingIds = visibleWidgets
          .filter((w) => !filtered.some((item) => item.i === w.id))
          .map((w) => defaults.find((d) => d.i === w.id)!)
          .filter(Boolean)
        result[bp] = [...filtered, ...missingIds]
      } else {
        result[bp] = defaults.filter((d) =>
          visibleWidgets.some((w) => w.id === d.i)
        )
      }
    }
    return result
  }, [storedLayouts, visibleWidgets])

  // Persist on layout change (all breakpoints at once)
  const handleLayoutChange = useCallback(
    (_currentLayout: Layout, allLayouts: ResponsiveLayouts) => {
      // Convert readonly Layout to mutable LayoutItem[] for storage
      const mutableLayouts: Record<string, LayoutItem[]> = {}
      for (const [bp, layout] of Object.entries(allLayouts)) {
        if (layout) {
          mutableLayouts[bp] = [...layout] as LayoutItem[]
        }
      }
      setLayouts(mutableLayouts)
    },
    [setLayouts]
  )

  // Hydration guard -- prevent layout flash
  const hasHydrated = useDashboardStore.persist.hasHydrated()

  if (!hasHydrated || !mounted) {
    return (
      <div ref={containerRef} className="min-h-[200px]">
        <WidgetSkeleton />
      </div>
    )
  }

  if (visibleWidgets.length === 0) {
    return (
      <div ref={containerRef}>
        <div className="flex flex-col items-center justify-center py-16 gap-4">
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            {t('widgets.no_widgets')}
          </p>
          <button
            onClick={onOpenSettings}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all duration-150 hover:opacity-90"
            style={{
              backgroundColor: 'var(--accent)',
              color: 'var(--bg-primary)',
            }}
          >
            <Settings2 size={14} />
            {t('widgets.customize')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div ref={containerRef}>
      <ResponsiveGridLayout
        width={width}
        layouts={mergedLayouts}
        breakpoints={BREAKPOINTS}
        cols={COLS}
        rowHeight={60}
        margin={[12, 12]}
        dragConfig={{ enabled: true, handle: '.widget-drag-handle', threshold: 3 }}
        resizeConfig={{ enabled: true, handles: ['se'] }}
        onLayoutChange={handleLayoutChange}
      >
        {visibleWidgets.map((widget) => {
          const Widget = widget.component
          return (
            <div key={widget.id}>
              <WidgetWrapper
                definition={widget}
                onRemove={() => toggleWidget(widget.id)}
                noPadding={NO_PADDING_WIDGETS.has(widget.id)}
              >
                <Suspense fallback={<WidgetSkeleton />}>
                  <Widget />
                </Suspense>
              </WidgetWrapper>
            </div>
          )
        })}
      </ResponsiveGridLayout>
    </div>
  )
}
