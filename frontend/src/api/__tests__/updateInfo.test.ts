/**
 * GET /update is rate-limited by the backend; a 429 must resolve quietly as
 * "no update info" instead of rejecting (which would log an error and retry).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('../core', () => ({ api: { get } }))

import { getUpdateInfo } from '../health'

describe('getUpdateInfo', () => {
  beforeEach(() => get.mockReset())

  it('returns the payload on 200', async () => {
    const info = { available: true, latest: '1.2.3', current: '1.2.2', url: 'https://x' }
    get.mockResolvedValue({ status: 200, data: info })
    await expect(getUpdateInfo()).resolves.toEqual(info)
  })

  it('returns null on 429 without throwing', async () => {
    get.mockResolvedValue({ status: 429, data: { error: 'rate limited' } })
    await expect(getUpdateInfo()).resolves.toBeNull()
  })

  it('accepts 429 as a non-error status', async () => {
    get.mockResolvedValue({ status: 200, data: {} })
    await getUpdateInfo()
    const { validateStatus } = get.mock.calls[0][1]
    expect(validateStatus(429)).toBe(true)
    expect(validateStatus(204)).toBe(true)
    expect(validateStatus(500)).toBe(false)
  })
})
