import { useState, useCallback, useEffect, useRef } from 'react'
import { CheckCircle2, XCircle, Info, X } from 'lucide-react'

type ToastType = 'success' | 'error' | 'info'

interface ToastMessage {
  id: number
  message: string
  type: ToastType
}

let toastIdCounter = 0

const listeners: Set<(toast: ToastMessage) => void> = new Set()

// eslint-disable-next-line react-refresh/only-export-components
export function toast(message: string, type: ToastType = 'success') {
  const t: ToastMessage = { id: ++toastIdCounter, message, type }
  listeners.forEach((fn) => fn(t))
}

const icons: Record<ToastType, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
}

const borderColors: Record<ToastType, string> = {
  success: 'var(--success)',
  error: 'var(--error)',
  info: 'var(--accent)',
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  const addToast = useCallback((t: ToastMessage) => {
    setToasts((prev) => [...prev, t])
    const timer = setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== t.id))
      timersRef.current.delete(t.id)
    }, 3500)
    timersRef.current.set(t.id, timer)
  }, [])

  useEffect(() => {
    listeners.add(addToast)
    const timers = timersRef.current
    return () => {
      listeners.delete(addToast)
      timers.forEach((timer) => clearTimeout(timer))
    }
  }, [addToast])

  const dismiss = (id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    const timer = timersRef.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timersRef.current.delete(id)
    }
  }

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => {
        const Icon = icons[t.type]
        return (
          <div
            key={t.id}
            className="flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              borderLeft: `3px solid ${borderColors[t.type]}`,
              color: 'var(--text-primary)',
              minWidth: '280px',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.3)',
              animation: 'slideInRight 0.3s ease-out both',
            }}
          >
            <Icon size={16} style={{ color: borderColors[t.type], flexShrink: 0 }} />
            <span className="flex-1">{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              className="p-0.5 rounded transition-colors"
              style={{ color: 'var(--text-muted)' }}
            >
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
