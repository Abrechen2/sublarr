import { useState, useEffect, useCallback, useRef } from 'react'
import { CheckCircle2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface AutoSaveToastProps {
  readonly visible: boolean
  readonly onUndo?: () => void
  readonly onDismiss?: () => void
  readonly message?: string
  readonly undoLabel?: string
  readonly dismissAfterMs?: number
  readonly className?: string
}

export function AutoSaveToast({
  visible,
  onUndo,
  onDismiss,
  message = 'Setting saved',
  undoLabel = 'Undo',
  dismissAfterMs = 3000,
  className,
}: AutoSaveToastProps) {
  const [shown, setShown] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const dismiss = useCallback(() => {
    clearTimer()
    setShown(false)
    onDismiss?.()
  }, [clearTimer, onDismiss])

  useEffect(() => {
    if (visible) {
      setShown(true)
      clearTimer()
      timerRef.current = setTimeout(() => {
        dismiss()
      }, dismissAfterMs)
    } else {
      dismiss()
    }

    return clearTimer
  }, [visible, dismissAfterMs, dismiss, clearTimer])

  const handleUndo = useCallback(() => {
    dismiss()
    onUndo?.()
  }, [dismiss, onUndo])

  if (!shown) return null

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-testid="auto-save-toast"
      className={cn(
        'fixed bottom-4 right-4 z-50',
        'flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium',
        className,
      )}
      style={{
        backgroundColor: 'var(--bg-elevated)',
        borderLeft: '3px solid var(--success)',
        color: 'var(--text-primary)',
        minWidth: '220px',
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.3)',
        animation: 'slideInRight 0.3s ease-out both',
      }}
    >
      <CheckCircle2
        size={16}
        style={{ color: 'var(--success)', flexShrink: 0 }}
        data-testid="auto-save-toast-icon"
      />
      <span data-testid="auto-save-toast-message" className="flex-1">
        {message}
      </span>
      {onUndo && (
        <button
          type="button"
          data-testid="auto-save-toast-undo"
          onClick={handleUndo}
          className={cn(
            'text-[12px] font-semibold px-2 py-0.5 rounded transition-colors',
            'hover:bg-[var(--bg-hover)]',
          )}
          style={{ color: 'var(--accent)' }}
        >
          {undoLabel}
        </button>
      )}
    </div>
  )
}
