/**
 * Dashboard layout persistence store.
 *
 * Stores widget layouts per breakpoint and hidden widget IDs in localStorage
 * via zustand persist middleware. Layout is keyed by breakpoint name
 * (lg, md, sm, xs, xxs) and each value is a Layout array from react-grid-layout.
 *
 * hiddenWidgets is a string[] (not Set) because JSON serialization requires
 * plain arrays.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { LayoutItem } from 'react-grid-layout'

interface DashboardState {
  /** Layouts keyed by breakpoint name */
  layouts: Record<string, LayoutItem[]>
  /** Array of hidden widget IDs */
  hiddenWidgets: string[]
}

interface DashboardActions {
  /** Update layout for all breakpoints (called on layout change) */
  setLayouts: (layouts: Record<string, LayoutItem[]>) => void
  /** Toggle a widget's visibility */
  toggleWidget: (widgetId: string) => void
  /** Reset layouts and visibility to defaults */
  resetToDefault: () => void
  /** Check if a widget is hidden */
  isWidgetHidden: (widgetId: string) => boolean
}

const INITIAL_STATE: DashboardState = {
  layouts: {},
  hiddenWidgets: [],
}

export const useDashboardStore = create<DashboardState & DashboardActions>()(
  persist(
    (set, get) => ({
      ...INITIAL_STATE,

      setLayouts: (layouts) =>
        set(() => ({
          layouts: { ...layouts },
        })),

      toggleWidget: (widgetId) =>
        set((state) => {
          const isHidden = state.hiddenWidgets.includes(widgetId)
          return {
            hiddenWidgets: isHidden
              ? state.hiddenWidgets.filter((id) => id !== widgetId)
              : [...state.hiddenWidgets, widgetId],
          }
        }),

      resetToDefault: () =>
        set(() => ({
          layouts: {},
          hiddenWidgets: [],
        })),

      isWidgetHidden: (widgetId) => get().hiddenWidgets.includes(widgetId),
    }),
    {
      name: 'sublarr-dashboard',
    }
  )
)
