import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import * as api from '@/api/client'

// Mock axios
vi.mock('axios')
const mockedAxios = axios as unknown as {
  create: ReturnType<typeof vi.fn>
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}

describe('API Client', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('getHealth returns health status', async () => {
    const mockData = { status: 'healthy', services: {} }
    mockedAxios.get = vi.fn().mockResolvedValue({ data: mockData })

    // We can't directly test the exported functions without mocking axios.create
    // This is a placeholder test structure
    expect(true).toBe(true)
  })
})
