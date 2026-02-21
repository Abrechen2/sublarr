import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useHotkeys } from 'react-hotkeys-hook'
import { Plus } from 'lucide-react'
import { getActionTemplatesForRoute } from './quickActionDefinitions'
import type { QuickActionTemplate } from './quickActionDefinitions'
import { useRefreshWanted, useSearchAllWanted, useStartWantedBatch } from '@/hooks/useApi'
import { useSelectionStore } from '@/stores/selectionStore'
import { toast } from '@/components/shared/Toast'

// ─── FAB Animation Styles ────────────────────────────────────────────────────

const fabStyles = `
@keyframes fadeSlideUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
`

// ─── Action Handler Hook ─────────────────────────────────────────────────────

function useQuickActionHandlers(): ReadonlyMap<string, () => void> {
  const refreshWanted = useRefreshWanted()
  const searchAllWanted = useSearchAllWanted()
  const startWantedBatch = useStartWantedBatch()
  const selectAllItems = useSelectionStore((s) => s.selectAll)

  return useMemo(() => {
    const handlers = new Map<string, () => void>()

    handlers.set('scan_library', () => {
      void refreshWanted.mutateAsync(undefined)
      toast('Library scan started', 'info')
    })

    handlers.set('search_wanted', () => {
      void searchAllWanted.mutateAsync(undefined)
      toast('Wanted search started', 'info')
    })

    handlers.set('refresh_scan', () => {
      void refreshWanted.mutateAsync(undefined)
      toast('Refresh scan started', 'info')
    })

    handlers.set('search_all', () => {
      void startWantedBatch.mutateAsync(undefined)
      toast('Batch search started', 'info')
    })

    handlers.set('select_all', () => {
      // Select all is a toggle -- handled by the page's own selection logic
      // Here we just notify, the actual selection is managed by selection store
      selectAllItems('wanted', [])
      toast('Selection toggled', 'info')
    })

    handlers.set('health_check', () => {
      toast('Health check: use the episode table actions', 'info')
    })

    return handlers
  }, [refreshWanted, searchAllWanted, startWantedBatch, selectAllItems])
}

// ─── FAB Component ───────────────────────────────────────────────────────────

export function QuickActionsFAB() {
  const [open, setOpen] = useState(false)
  const fabRef = useRef<HTMLDivElement>(null)
  const { pathname } = useLocation()
  const { t } = useTranslation('common')
  const handlers = useQuickActionHandlers()

  const actions = useMemo(
    () => getActionTemplatesForRoute(pathname),
    [pathname],
  )

  // Close FAB when route changes
  useEffect(() => {
    setOpen(false)
  }, [pathname])

  const handleAction = useCallback(
    (action: QuickActionTemplate) => {
      const handler = handlers.get(action.id)
      if (handler) handler()
      setOpen(false)
    },
    [handlers],
  )

  const toggleOpen = useCallback(() => {
    setOpen((prev) => !prev)
  }, [])

  const closeMenu = useCallback(() => {
    setOpen(false)
  }, [])

  // Register page-specific hotkeys for each action
  const hotkeyStr = actions.map((a) => a.hotkeyCombo).join(', ')

  useHotkeys(
    hotkeyStr || 'never-match-this-key-combo',
    (event, hotkeysEvent) => {
      const pressedCombo = hotkeysEvent.keys?.join('+') ?? ''
      const matchedAction = actions.find((a) => {
        // Normalize both combos for comparison
        const normalized = a.hotkeyCombo.replace(/\+/g, '+').toLowerCase()
        return normalized === `shift+${pressedCombo}` || normalized === pressedCombo
      })
      if (matchedAction) {
        const handler = handlers.get(matchedAction.id)
        if (handler) handler()
      }
    },
    {
      preventDefault: true,
      enabled: actions.length > 0,
    },
    [actions, handlers],
  )

  // Hide FAB if no actions for current route
  if (actions.length === 0) return null

  return (
    <>
      <style>{fabStyles}</style>

      {/* Overlay to close on outside click */}
      {open && (
        <div
          className="fixed inset-0 z-40"
          onClick={closeMenu}
          aria-hidden="true"
        />
      )}

      <div ref={fabRef} className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-2">
        {/* Action items (shown when open) */}
        {open && actions.map((action, index) => {
          const Icon = action.icon
          return (
            <button
              key={action.id}
              onClick={() => handleAction(action)}
              className="flex items-center gap-3 rounded-full px-4 py-2 shadow-lg transition-colors"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                color: 'var(--text)',
                animation: `fadeSlideUp 0.2s ease-out ${index * 0.05}s both`,
              }}
            >
              <Icon size={16} style={{ color: 'var(--accent)' }} />
              <span className="whitespace-nowrap text-sm font-medium">
                {t(action.labelKey.replace('common:', ''))}
              </span>
              <kbd
                className="rounded px-1.5 py-0.5 font-mono text-xs"
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                }}
              >
                {action.shortcut}
              </kbd>
            </button>
          )
        })}

        {/* Main FAB button */}
        <button
          onClick={toggleOpen}
          className="flex h-12 w-12 items-center justify-center rounded-full shadow-lg transition-transform duration-200"
          style={{
            backgroundColor: 'var(--accent)',
            color: 'white',
            transform: open ? 'rotate(45deg)' : 'rotate(0deg)',
          }}
          aria-label={open ? 'Close quick actions' : 'Open quick actions'}
          aria-expanded={open}
        >
          <Plus size={24} />
        </button>
      </div>
    </>
  )
}
