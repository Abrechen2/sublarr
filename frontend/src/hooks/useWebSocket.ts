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

    if (options.onJobUpdate) {
      socket.on('job_update', options.onJobUpdate)
    }
    if (options.onBatchProgress) {
      socket.on('batch_progress', options.onBatchProgress)
    }
    if (options.onBatchCompleted) {
      socket.on('batch_completed', options.onBatchCompleted)
    }
    if (options.onLogEntry) {
      socket.on('log_entry', options.onLogEntry)
    }

    socketRef.current = socket

    return () => {
      socket.disconnect()
    }
  }, [])

  const emit = useCallback((event: string, data?: unknown) => {
    socketRef.current?.emit(event, data)
  }, [])

  return { connected, emit, socket: socketRef }
}
