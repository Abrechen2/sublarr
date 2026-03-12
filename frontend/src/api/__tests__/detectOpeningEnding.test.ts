import { describe, it, expect, vi } from 'vitest'

vi.mock('axios', () => ({
  default: {
    create: () => ({
      post: vi.fn().mockResolvedValue({ data: { status: 'detected', detected: [] } }),
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    }),
  },
}))

describe('detectOpeningEnding', () => {
  it('is exported from client.ts and returns detected array', async () => {
    const { detectOpeningEnding } = await import('../client')
    expect(typeof detectOpeningEnding).toBe('function')
    const result = await detectOpeningEnding('/media/test.ass')
    expect(result).toHaveProperty('status', 'detected')
    expect(Array.isArray(result.detected)).toBe(true)
  })
})
