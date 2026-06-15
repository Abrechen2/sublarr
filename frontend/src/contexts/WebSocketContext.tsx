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
    const apikey = localStorage.getItem('sublarr_api_key') ?? undefined
    socketRef.current = io(window.location.origin, {
      // Polling-only by design. The backend runs Flask-SocketIO with
      // async_mode="threading" (gunicorn gthread worker, see backend/app.py),
      // which does NOT implement the native WebSocket transport — every
      // attempted `websocket` upgrade fails its handshake (404/400) and spams
      // the browser console with errors before silently falling back to
      // long-polling (GitHub #148). The Werkzeug dev server has the same
      // limitation. Until the server moves to an eventlet/gevent async mode,
      // long-polling is the only transport that actually works, so don't
      // advertise `websocket` to the client.
      transports: ['polling'],
      auth: apikey ? { apikey } : undefined,
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
// eslint-disable-next-line react-refresh/only-export-components
export function useSocket(): Socket | null {
  try {
    return useContext(WebSocketContext)
  } catch {
    // dispatcher is null when multiple React instances exist (e.g. some deps bundle their own React)
    return null
  }
}
