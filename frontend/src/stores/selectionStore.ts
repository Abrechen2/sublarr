/**
 * Zustand store for cross-page multi-select state.
 *
 * Uses a scope string per page ('wanted', 'library', 'history') so selections
 * on different pages are independent and survive navigation.
 *
 * Shift+click range selection operates on the orderedIds of the CURRENT PAGE
 * only to avoid cross-page range bugs.
 */
import { create } from 'zustand'

interface SelectionState {
  /** Map from scope to Set of selected IDs */
  selections: Record<string, Set<number>>
  /** Last clicked item index per scope (for Shift+click range) */
  lastClickedIndex: Record<string, number | null>
}

interface SelectionActions {
  toggleItem: (scope: string, id: number, index: number, shiftKey: boolean, orderedIds: number[]) => void
  selectAll: (scope: string, ids: number[]) => void
  clearSelection: (scope: string) => void
  getSelected: (scope: string) => Set<number>
  getSelectedArray: (scope: string) => number[]
  isSelected: (scope: string, id: number) => boolean
  getCount: (scope: string) => number
}

export const useSelectionStore = create<SelectionState & SelectionActions>((set, get) => ({
  selections: {},
  lastClickedIndex: {},

  toggleItem: (scope, id, index, shiftKey, orderedIds) => {
    set((state) => {
      const current = new Set(state.selections[scope] ?? [])
      const lastIdx = state.lastClickedIndex[scope] ?? null

      if (shiftKey && lastIdx !== null) {
        const [from, to] = lastIdx < index ? [lastIdx, index] : [index, lastIdx]
        for (let i = from; i <= to; i++) {
          if (orderedIds[i] !== undefined) current.add(orderedIds[i])
        }
      } else {
        if (current.has(id)) {
          current.delete(id)
        } else {
          current.add(id)
        }
      }

      return {
        selections: { ...state.selections, [scope]: current },
        lastClickedIndex: { ...state.lastClickedIndex, [scope]: index },
      }
    })
  },

  selectAll: (scope, ids) =>
    set((state) => ({ selections: { ...state.selections, [scope]: new Set(ids) } })),

  clearSelection: (scope) =>
    set((state) => ({
      selections: { ...state.selections, [scope]: new Set() },
      lastClickedIndex: { ...state.lastClickedIndex, [scope]: null },
    })),

  getSelected: (scope) => get().selections[scope] ?? new Set(),
  getSelectedArray: (scope) => [...(get().selections[scope] ?? new Set())],
  isSelected: (scope, id) => (get().selections[scope] ?? new Set()).has(id),
  getCount: (scope) => (get().selections[scope] ?? new Set()).size,
}))
