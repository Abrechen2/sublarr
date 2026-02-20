/**
 * WebSocketContext — Single shared Socket.IO connection for the entire app.
 *
 * Wrapping the app with <WebSocketProvider> ensures only ONE socket is created
 * regardless of how many components call useWebSocket(). Previously each
 * useWebSocket() call opened its own connection (C7 fix).
 */
import { createContext, useContext, useEffect, useRef } from 'react'
import { io, type Socket } from 'socket.io-client'

const WebSocketContext = createContext<Socket | null>(null)

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const socketRef = useRef<Socket | null>(null)

  if (socketRef.current === null) {
    // Create synchronously so context value is stable on first render
    socketRef.current = io(window.location.origin, {
      transports: ['websocket', 'polling'],
    })
  }

  useEffect(() => {
    const socket = socketRef.current
    return () => {
      socket?.disconnect()
    }
  }, [])

  return (
    <WebSocketContext.Provider value={socketRef.current}>
      {children}
    </WebSocketContext.Provider>
  )
}

/** Returns the shared Socket.IO instance (null if used outside <WebSocketProvider> or if dispatcher is null). */
export function useSocket(): Socket | null {
  try {
    return useContext(WebSocketContext)
  } catch {
    // dispatcher is null when multiple React instances exist (e.g. some deps bundle their own React)
    return null
  }
}
