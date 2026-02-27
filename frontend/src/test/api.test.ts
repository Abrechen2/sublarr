import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock axios before importing client (client.ts sets up interceptors at module level)
vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
    })),
  },
}))

import * as _api from '@/api/client'

describe('API Client', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('module loads without errors', () => {
    // Verifies the client module initialises correctly when axios is mocked
    expect(_api).toBeDefined()
  })
})
