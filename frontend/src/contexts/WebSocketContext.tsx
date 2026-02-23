/**
 * WebSocketContext — Single shared Socket.IO connection for the entire app.
 *
 * Wrapping the app with <WebSocketProvider> ensures only ONE socket is created
 * regardless of how many components call useWebSocket(). Previously each
 * useWebSocket() call opened its own connection (C7 fix).
 *
 * Fix 4: Socket is created inside useEffect, not as a render side-effect, to
 * avoid running IO calls during React's render phase.
 */
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { io, type Socket } from 'socket.io-client'

const WebSocketContext = createContext<Socket | null>(null)

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const socketRef = useRef<Socket | null>(null)
  // Use state so consumers re-render once the socket is available after mount
  const [socket, setSocket] = useState<Socket | null>(null)

  useEffect(() => {
    socketRef.current = io(window.location.origin, {
      transports: ['websocket', 'polling'],
    })
    setSocket(socketRef.current)

    return () => {
      socketRef.current?.disconnect()
      socketRef.current = null
      setSocket(null)
    }
  }, [])

  return (
    <WebSocketContext.Provider value={socket}>
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
