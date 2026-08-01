import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { api, bootstrapApiKey } from './core'

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

describe('401 response interceptor', () => {
  // The interceptor is registered on the `api` instance at module load;
  // invoke its rejection handler directly to simulate a failed response.
  const rejected = (api.interceptors.response as unknown as {
    handlers: Array<{ rejected: (error: unknown) => Promise<unknown> }>
  }).handlers[0].rejected

  beforeEach(() => {
    localStorage.clear()
  })

  it('clears a stale stored key on 401 so the next load re-bootstraps', async () => {
    localStorage.setItem('sublarr_api_key', 'stale-key')
    await expect(
      rejected({ response: { status: 401 }, config: { url: '/wanted' } })
    ).rejects.toBeTruthy()
    expect(localStorage.getItem('sublarr_api_key')).toBeNull()
  })

  it('keeps the stored key on 401 from auth endpoints (wrong password)', async () => {
    localStorage.setItem('sublarr_api_key', 'valid-key')
    await expect(
      rejected({ response: { status: 401 }, config: { url: '/auth/login' } })
    ).rejects.toBeTruthy()
    expect(localStorage.getItem('sublarr_api_key')).toBe('valid-key')
  })

  describe('redirect behaviour', () => {
    const original = window.location
    let assigned: string | null

    const stubLocation = (pathname: string) => {
      assigned = null
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: {
          pathname,
          get href() {
            return `http://localhost${pathname}`
          },
          set href(value: string) {
            assigned = value
          },
        },
      })
    }

    afterEach(() => {
      Object.defineProperty(window, 'location', { configurable: true, value: original })
    })

    it('redirects to /login on a 401 raised from another page', async () => {
      stubLocation('/wanted')
      await expect(
        rejected({ response: { status: 401 }, config: { url: '/wanted' } })
      ).rejects.toBeTruthy()
      expect(assigned).toBe('/login')
    })

    it('does NOT redirect when already on /login (would reload-loop)', async () => {
      stubLocation('/login')
      await expect(
        rejected({ response: { status: 401 }, config: { url: '/wanted' } })
      ).rejects.toBeTruthy()
      expect(assigned).toBeNull()
    })
  })
})
