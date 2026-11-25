import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { attachReconnect, notifyAuthChanged } from '../socketReconnect'

/** The part of a socket.io client the helper uses. */
function fakeSocket() {
  const handlers: Record<string, Array<() => void>> = {}
  return {
    connected: false,
    active: false,
    connect: vi.fn(),
    on(ev: string, fn: () => void) { (handlers[ev] ??= []).push(fn) },
    off(ev: string, fn: () => void) { handlers[ev] = (handlers[ev] ?? []).filter(h => h !== fn) },
    emit(ev: string) { (handlers[ev] ?? []).forEach(h => h()) },
  }
}

describe('attachReconnect', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('reconnects after the server refused the handshake', () => {
    // A refusal (no session yet) stops socket.io for good: socket.active is
    // false and it never retries, so live updates stayed dead after login.
    const s = fakeSocket()
    attachReconnect(s, { baseMs: 1000, maxMs: 8000 })
    s.emit('connect_error')
    vi.advanceTimersByTime(999)
    expect(s.connect).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(s.connect).toHaveBeenCalledTimes(1)
  })

  it('backs off up to the maximum and resets after a connect', () => {
    const s = fakeSocket()
    attachReconnect(s, { baseMs: 1000, maxMs: 4000 })
    for (const wait of [1000, 2000, 4000, 4000]) {
      s.connect.mockClear()
      s.emit('connect_error')
      vi.advanceTimersByTime(wait - 1)
      expect(s.connect).not.toHaveBeenCalled()
      vi.advanceTimersByTime(1)
      expect(s.connect).toHaveBeenCalledTimes(1)
    }
    s.emit('connect')
    s.connect.mockClear()
    s.emit('connect_error')
    vi.advanceTimersByTime(1000)
    expect(s.connect).toHaveBeenCalledTimes(1)
  })

  it('leaves retries to socket.io while it is still retrying itself', () => {
    const s = fakeSocket()
    s.active = true
    attachReconnect(s, { baseMs: 1000, maxMs: 4000 })
    s.emit('connect_error')
    vi.advanceTimersByTime(10_000)
    expect(s.connect).not.toHaveBeenCalled()
  })

  it('connects at once when the sign-in state changes', () => {
    const s = fakeSocket()
    attachReconnect(s, { baseMs: 60_000, maxMs: 60_000 })
    s.emit('connect_error')
    notifyAuthChanged()
    expect(s.connect).toHaveBeenCalledTimes(1)
    // The pending backoff retry is dropped, not doubled up.
    vi.advanceTimersByTime(60_000)
    expect(s.connect).toHaveBeenCalledTimes(1)
  })

  it('does nothing on a sign-in change while connected', () => {
    const s = fakeSocket()
    s.connected = true
    attachReconnect(s, { baseMs: 1000, maxMs: 1000 })
    notifyAuthChanged()
    expect(s.connect).not.toHaveBeenCalled()
  })

  it('stops after cleanup', () => {
    const s = fakeSocket()
    const stop = attachReconnect(s, { baseMs: 1000, maxMs: 1000 })
    s.emit('connect_error')
    stop()
    vi.advanceTimersByTime(5000)
    notifyAuthChanged()
    expect(s.connect).not.toHaveBeenCalled()
  })
})
