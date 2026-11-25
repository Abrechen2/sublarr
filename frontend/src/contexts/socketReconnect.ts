/**
 * Keeps the live connection coming back after the server refused it.
 *
 * Since #79 the Socket.IO handshake follows the API gate: without a UI session
 * (login page, expired session) the server refuses it. socket.io-client treats
 * a refusal as final (`socket.active` is false) and never retries, so live
 * updates stayed dead after signing in until the page was reloaded.
 */

const AUTH_CHANGED_EVENT = 'sublarr:auth-changed'

/** The part of a socket.io client this helper uses. */
export interface ReconnectableSocket {
  readonly connected: boolean
  readonly active: boolean
  connect(): unknown
  on(event: string, fn: () => void): unknown
  off(event: string, fn: () => void): unknown
}

export interface ReconnectOptions {
  baseMs: number
  maxMs: number
}

export const DEFAULT_RECONNECT: ReconnectOptions = { baseMs: 2_000, maxMs: 30_000 }

/** Tell the live connection that the sign-in state changed (login, setup). */
export function notifyAuthChanged(): void {
  window.dispatchEvent(new Event(AUTH_CHANGED_EVENT))
}

/** Retry a refused handshake with backoff, and at once on a sign-in change. */
export function attachReconnect(
  socket: ReconnectableSocket,
  { baseMs, maxMs }: ReconnectOptions = DEFAULT_RECONNECT,
): () => void {
  let delay = baseMs
  let timer: ReturnType<typeof setTimeout> | null = null

  const clearTimer = () => {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }
  const onConnectError = () => {
    // While socket.io is still retrying on its own (network errors), leave it.
    if (socket.active || timer !== null) return
    timer = setTimeout(() => {
      timer = null
      socket.connect()
    }, delay)
    delay = Math.min(delay * 2, maxMs)
  }
  const onConnect = () => {
    clearTimer()
    delay = baseMs
  }
  const onAuthChanged = () => {
    if (socket.connected) return
    clearTimer()
    socket.connect()
  }

  socket.on('connect_error', onConnectError)
  socket.on('connect', onConnect)
  window.addEventListener(AUTH_CHANGED_EVENT, onAuthChanged)
  return () => {
    clearTimer()
    socket.off('connect_error', onConnectError)
    socket.off('connect', onConnect)
    window.removeEventListener(AUTH_CHANGED_EVENT, onAuthChanged)
  }
}
