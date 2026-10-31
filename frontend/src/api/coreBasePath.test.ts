import { describe, it, expect, vi, afterEach } from 'vitest'

// Audit #61 A31: behind a reverse-proxy prefix the API and bootstrap used the
// prefix, but a 401 sent the browser to "/login" — outside the app.
describe('401 redirect under a path prefix', () => {
  const original = window.location

  afterEach(() => {
    Object.defineProperty(window, 'location', { configurable: true, value: original })
    document.head.querySelector('base')?.remove()
    vi.resetModules()
  })

  it('goes to <prefix>/login and does not loop there', async () => {
    const base = document.createElement('base')
    base.setAttribute('href', '/sublarr/')
    document.head.appendChild(base)
    vi.resetModules()
    const { api } = await import('./core')
    const rejected = (api.interceptors.response as unknown as {
      handlers: Array<{ rejected: (error: unknown) => Promise<unknown> }>
    }).handlers[0].rejected

    let assigned: string | null = null
    const stub = (pathname: string) =>
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: { pathname, set href(v: string) { assigned = v }, get href() { return pathname } },
      })

    stub('/sublarr/wanted')
    await expect(rejected({ response: { status: 401 }, config: { url: '/wanted' } })).rejects.toBeTruthy()
    expect(assigned).toBe('/sublarr/login')

    assigned = null
    stub('/sublarr/login')
    await expect(rejected({ response: { status: 401 }, config: { url: '/wanted' } })).rejects.toBeTruthy()
    expect(assigned).toBeNull()
  })
})

describe('development mocks', () => {
  it('never turn a failed write into a success', async () => {
    vi.resetModules()
    const { api } = await import('./core')
    const rejected = (api.interceptors.response as unknown as {
      handlers: Array<{ rejected: (error: unknown) => Promise<unknown> }>
    }).handlers[0].rejected

    await expect(
      rejected({ response: { status: 500 }, config: { url: '/config', method: 'put' } }),
    ).rejects.toBeTruthy()
  })
})
