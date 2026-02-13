import { useEffect, useRef, useCallback, useState } from 'react'
import { io, type Socket } from 'socket.io-client'

interface UseWebSocketOptions {
  onJobUpdate?: (data: unknown) => void
  onBatchProgress?: (data: unknown) => void
  onBatchCompleted?: (data: unknown) => void
  onLogEntry?: (data: unknown) => void
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const socketRef = useRef<Socket | null>(null)
  const [connected, setConnected] = useState(false)

  // Keep stable refs for callbacks to avoid stale closures
  const onJobUpdateRef = useRef(options.onJobUpdate)
  const onBatchProgressRef = useRef(options.onBatchProgress)
  const onBatchCompletedRef = useRef(options.onBatchCompleted)
  const onLogEntryRef = useRef(options.onLogEntry)

  // Update refs when callbacks change
  useEffect(() => {
    onJobUpdateRef.current = options.onJobUpdate
    onBatchProgressRef.current = options.onBatchProgress
    onBatchCompletedRef.current = options.onBatchCompleted
    onLogEntryRef.current = options.onLogEntry
  }, [options.onJobUpdate, options.onBatchProgress, options.onBatchCompleted, options.onLogEntry])

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
    socket.on('job_update', (data: unknown) => {
      onJobUpdateRef.current?.(data)
    })
    socket.on('batch_progress', (data: unknown) => {
      onBatchProgressRef.current?.(data)
    })
    socket.on('batch_completed', (data: unknown) => {
      onBatchCompletedRef.current?.(data)
    })
    socket.on('log_entry', (data: unknown) => {
      onLogEntryRef.current?.(data)
    })

    socketRef.current = socket

    return () => {
      socket.off('job_update')
      socket.off('batch_progress')
      socket.off('batch_completed')
      socket.off('log_entry')
      socket.disconnect()
    }
  }, [])

  const emit = useCallback((event: string, data?: unknown) => {
    socketRef.current?.emit(event, data)
  }, [])

  return { connected, emit, socket: socketRef }
}
