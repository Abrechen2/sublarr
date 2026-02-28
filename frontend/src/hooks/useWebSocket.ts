import { useEffect, useRef, useCallback, useState } from 'react'
import type { SyncBatchProgress, SyncBatchComplete } from '@/lib/types'
import { useSocket } from '@/contexts/WebSocketContext'

interface UseWebSocketOptions {
  onJobUpdate?: (data: unknown) => void
  onBatchProgress?: (data: unknown) => void
  onBatchCompleted?: (data: unknown) => void
  onLogEntry?: (data: unknown) => void
  onWebhookReceived?: (data: unknown) => void
  onWebhookCompleted?: (data: unknown) => void
  onUpgradeCompleted?: (data: unknown) => void
  onWantedScanCompleted?: (data: unknown) => void
  onWantedScanProgress?: (data: unknown) => void
  onWantedSearchProgress?: (data: unknown) => void
  onWantedSearchCompleted?: (data: unknown) => void
  onWantedBatchProgress?: (data: unknown) => void
  onWantedBatchCompleted?: (data: unknown) => void
  onBatchExtractProgress?: (data: unknown) => void
  onBatchExtractCompleted?: (data: unknown) => void
  onRetranslationProgress?: (data: unknown) => void
  onRetranslationCompleted?: (data: unknown) => void
  onConfigUpdated?: (data: unknown) => void
  onSyncBatchProgress?: (data: SyncBatchProgress) => void
  onSyncBatchComplete?: (data: SyncBatchComplete) => void
  onBatchProbeProgress?: (data: unknown) => void
  onBatchProbeCompleted?: (data: unknown) => void
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const socket = useSocket()
  const [connected, setConnected] = useState(() => socket?.connected ?? false)

  // Keep stable refs for callbacks to avoid stale closures
  const callbackRefs = useRef(options)

  // Update refs when callbacks change
  useEffect(() => {
    callbackRefs.current = options
  })

  // Register event listeners on the shared socket with proper cleanup
  useEffect(() => {
    if (!socket) return

    const handleConnect = () => setConnected(true)
    const handleDisconnect = () => setConnected(false)

    socket.on('connect', handleConnect)
    socket.on('disconnect', handleDisconnect)

    const events: Array<[string, keyof UseWebSocketOptions]> = [
      ['job_update', 'onJobUpdate'],
      ['batch_progress', 'onBatchProgress'],
      ['batch_completed', 'onBatchCompleted'],
      ['log_entry', 'onLogEntry'],
      ['webhook_received', 'onWebhookReceived'],
      ['webhook_completed', 'onWebhookCompleted'],
      ['upgrade_completed', 'onUpgradeCompleted'],
      ['wanted_scan_completed', 'onWantedScanCompleted'],
      ['wanted_scan_progress', 'onWantedScanProgress'],
      ['wanted_search_progress', 'onWantedSearchProgress'],
      ['wanted_search_completed', 'onWantedSearchCompleted'],
      ['wanted_batch_progress', 'onWantedBatchProgress'],
      ['wanted_batch_completed', 'onWantedBatchCompleted'],
      ['batch_extract_progress', 'onBatchExtractProgress'],
      ['batch_extract_completed', 'onBatchExtractCompleted'],
      ['retranslation_progress', 'onRetranslationProgress'],
      ['retranslation_completed', 'onRetranslationCompleted'],
      ['config_updated', 'onConfigUpdated'],
      ['sync_batch_progress', 'onSyncBatchProgress'],
      ['sync_batch_complete', 'onSyncBatchComplete'],
      ['batch_probe_progress', 'onBatchProbeProgress'],
      ['batch_probe_completed', 'onBatchProbeCompleted'],
    ]

    // Store named handler references so only this hook's listeners are removed on cleanup
    const handlers: Array<[string, (data: unknown) => void]> = events.map(
      ([eventName, callbackKey]) => {
        const handler = (data: unknown) => {
          ;(callbackRefs.current[callbackKey] as ((d: unknown) => void) | undefined)?.(data)
        }
        socket.on(eventName, handler)
        return [eventName, handler]
      }
    )

    return () => {
      socket.off('connect', handleConnect)
      socket.off('disconnect', handleDisconnect)
      for (const [eventName, handler] of handlers) {
        socket.off(eventName, handler)
      }
    }
  }, [socket])

  const emit = useCallback((event: string, data?: unknown) => {
    socket?.emit(event, data)
  }, [socket])

  return { connected, emit, socket }
}
