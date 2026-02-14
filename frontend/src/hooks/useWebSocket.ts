import { useEffect, useRef, useCallback, useState } from 'react'
import { io, type Socket } from 'socket.io-client'

interface UseWebSocketOptions {
  onJobUpdate?: (data: unknown) => void
  onBatchProgress?: (data: unknown) => void
  onBatchCompleted?: (data: unknown) => void
  onLogEntry?: (data: unknown) => void
  onWebhookReceived?: (data: unknown) => void
  onWebhookCompleted?: (data: unknown) => void
  onUpgradeCompleted?: (data: unknown) => void
  onWantedScanCompleted?: (data: unknown) => void
  onWantedSearchProgress?: (data: unknown) => void
  onWantedSearchCompleted?: (data: unknown) => void
  onWantedBatchProgress?: (data: unknown) => void
  onWantedBatchCompleted?: (data: unknown) => void
  onRetranslationProgress?: (data: unknown) => void
  onRetranslationCompleted?: (data: unknown) => void
  onConfigUpdated?: (data: unknown) => void
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const socketRef = useRef<Socket | null>(null)
  const [connected, setConnected] = useState(false)

  // Keep stable refs for callbacks to avoid stale closures
  const callbackRefs = useRef(options)

  // Update refs when callbacks change
  useEffect(() => {
    callbackRefs.current = options
  })

  // Stable socket connection — runs once
  useEffect(() => {
    const socket = io(window.location.origin, {
      transports: ['websocket', 'polling'],
    })

    socket.on('connect', () => {
      setConnected(true)
    })

    socket.on('disconnect', () => {
      setConnected(false)
    })

    // Use ref-based handlers so they always call the latest callback
    const events: Array<[string, keyof UseWebSocketOptions]> = [
      ['job_update', 'onJobUpdate'],
      ['batch_progress', 'onBatchProgress'],
      ['batch_completed', 'onBatchCompleted'],
      ['log_entry', 'onLogEntry'],
      ['webhook_received', 'onWebhookReceived'],
      ['webhook_completed', 'onWebhookCompleted'],
      ['upgrade_completed', 'onUpgradeCompleted'],
      ['wanted_scan_completed', 'onWantedScanCompleted'],
      ['wanted_search_progress', 'onWantedSearchProgress'],
      ['wanted_search_completed', 'onWantedSearchCompleted'],
      ['wanted_batch_progress', 'onWantedBatchProgress'],
      ['wanted_batch_completed', 'onWantedBatchCompleted'],
      ['retranslation_progress', 'onRetranslationProgress'],
      ['retranslation_completed', 'onRetranslationCompleted'],
      ['config_updated', 'onConfigUpdated'],
    ]

    for (const [eventName, callbackKey] of events) {
      socket.on(eventName, (data: unknown) => {
        callbackRefs.current[callbackKey]?.(data)
      })
    }

    socketRef.current = socket

    return () => {
      for (const [eventName] of events) {
        socket.off(eventName)
      }
      socket.disconnect()
    }
  }, [])

  const emit = useCallback((event: string, data?: unknown) => {
    socketRef.current?.emit(event, data)
  }, [])

  return { connected, emit, socket: socketRef }
}
