import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { bootstrapApiKey } from './core'

vi.mock('axios', async () => {
  const actual = await vi.importActual<typeof import('axios')>('axios')
  return {
    ...actual,
    default: {
      ...actual.default,
      create: actual.default.create,
      get: vi.fn(),
      post: vi.fn(),
    },
  }
})

describe('bootstrapApiKey', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('does nothing if a key is already stored', async () => {
    localStorage.setItem('sublarr_api_key', 'existing-key')
    await bootstrapApiKey()
    expect(axios.get).not.toHaveBeenCalled()
  })

  it('calls the no-op login before bootstrap when auth is disabled and unauthenticated', async () => {
    ;(axios.get as any).mockImplementation((url: string) => {
      if (url.includes('/auth/status')) {
        return Promise.resolve({ data: { enabled: false, authenticated: false, configured: true } })
      }
      if (url.includes('/auth/bootstrap')) {
        return Promise.resolve({ data: { api_key: 'fetched-key' } })
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })
    ;(axios.post as any).mockResolvedValue({ data: { status: 'ok' } })

    await bootstrapApiKey()

    expect(axios.post).toHaveBeenCalledWith('/api/v1/auth/login', {})
    expect(localStorage.getItem('sublarr_api_key')).toBe('fetched-key')
  })

  it('skips login when already authenticated', async () => {
    ;(axios.get as any).mockImplementation((url: string) => {
      if (url.includes('/auth/status')) {
        return Promise.resolve({ data: { enabled: false, authenticated: true, configured: true } })
      }
      if (url.includes('/auth/bootstrap')) {
        return Promise.resolve({ data: { api_key: 'fetched-key' } })
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })

    await bootstrapApiKey()

    expect(axios.post).not.toHaveBeenCalled()
    expect(localStorage.getItem('sublarr_api_key')).toBe('fetched-key')
  })

  it('skips login when auth is enabled', async () => {
    ;(axios.get as any).mockImplementation((url: string) => {
      if (url.includes('/auth/status')) {
        return Promise.resolve({ data: { enabled: true, authenticated: false, configured: true } })
      }
      if (url.includes('/auth/bootstrap')) {
        return Promise.reject({ response: { status: 403 } })
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })

    await bootstrapApiKey()

    expect(axios.post).not.toHaveBeenCalled()
    expect(localStorage.getItem('sublarr_api_key')).toBeNull()
  })

  it('still attempts bootstrap if the status check itself fails', async () => {
    ;(axios.get as any).mockImplementation((url: string) => {
      if (url.includes('/auth/status')) {
        return Promise.reject(new Error('network error'))
      }
      if (url.includes('/auth/bootstrap')) {
        return Promise.resolve({ data: { api_key: 'fetched-key' } })
      }
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })

    await bootstrapApiKey()

    expect(axios.post).not.toHaveBeenCalled()
    expect(localStorage.getItem('sublarr_api_key')).toBe('fetched-key')
  })
})
