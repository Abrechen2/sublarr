/**
 * Floating batch action bar shown at the bottom of the screen when items are selected.
 *
 * Renders: "{N} items selected . [Ignore] [Unignore] [Blacklist] [Export] [Clear]"
 * Disappears when selection count drops to 0.
 */
import { useState, useRef, useEffect } from 'react'
import { X, EyeOff, Eye, Ban, Download } from 'lucide-react'
import { useSelectionStore } from '@/stores/selectionStore'
import { useBatchAction } from '@/hooks/useApi'
import type { BatchAction, FilterScope } from '@/lib/types'

interface BatchActionDef {
  action: BatchAction
  label: string
  icon: React.ReactNode
  variant?: 'default' | 'destructive'
}

interface Props {
  scope: FilterScope
  /** Which actions to show for this page */
  actions?: BatchAction[]
  onActionComplete?: (action: BatchAction, result: unknown) => void
}

const ACTION_DEFS: BatchActionDef[] = [
  { action: 'ignore',    label: 'Ignore',    icon: <EyeOff className="h-3.5 w-3.5" /> },
  { action: 'unignore',  label: 'Unignore',  icon: <Eye className="h-3.5 w-3.5" /> },
  { action: 'blacklist', label: 'Blacklist',  icon: <Ban className="h-3.5 w-3.5" />, variant: 'destructive' },
  { action: 'export',    label: 'Export',     icon: <Download className="h-3.5 w-3.5" /> },
]

export function BatchActionBar({ scope, actions = ['ignore', 'unignore', 'blacklist', 'export'], onActionComplete }: Props) {
  const count = useSelectionStore((s) => s.getCount(scope))
  const getSelectedArray = useSelectionStore((s) => s.getSelectedArray)
  const clearSelection = useSelectionStore((s) => s.clearSelection)
  const batchMutation = useBatchAction()
  const [lastResult, setLastResult] = useState<string | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Fix 1: Clean up pending setTimeout on unmount to avoid state update on unmounted component
  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [])

  if (count === 0) return null

  const handleAction = async (action: BatchAction) => {
    const ids = getSelectedArray(scope)
    if (ids.length === 0) return

    if (action === 'export') {
      // Export: trigger download of selected item IDs as JSON
      const result = await batchMutation.mutateAsync({ itemIds: ids, action })
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const timestamp = new Date().getTime()
      a.download = `sublarr-export-${scope}-${String(timestamp)}.json`
      a.click()
      URL.revokeObjectURL(url)
      onActionComplete?.(action, result)
      return
    }

    const result = await batchMutation.mutateAsync({ itemIds: ids, action })
    setLastResult(`${result.affected} items updated`)
    timeoutRef.current = setTimeout(() => setLastResult(null), 3000)
    clearSelection(scope)
    onActionComplete?.(action, result)
  }

  const visibleActions = ACTION_DEFS.filter((a) => actions.includes(a.action))

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 px-4 py-2.5 bg-background border border-border rounded-full shadow-2xl shadow-black/20">
      <span className="text-sm font-medium text-foreground mr-1">
        {count} selected
      </span>
      <div className="h-4 w-px bg-border mx-1" />

      {visibleActions.map((def) => (
        <button
          key={def.action}
          onClick={() => void handleAction(def.action)}
          disabled={batchMutation.isPending}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors
            ${def.variant === 'destructive'
              ? 'bg-destructive/10 text-destructive hover:bg-destructive/20'
              : 'bg-muted text-muted-foreground hover:bg-accent hover:text-foreground'
            } disabled:opacity-50`}
        >
          {def.icon}
          {def.label}
        </button>
      ))}

      {lastResult && (
        <span className="text-xs text-teal-400 ml-1">{lastResult}</span>
      )}

      <div className="h-4 w-px bg-border mx-1" />
      <button
        onClick={() => clearSelection(scope)}
        className="p-1 text-muted-foreground hover:text-foreground rounded-full"
        aria-label="Clear selection"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}
