import { api } from './client'

export interface ProviderKey {
  id: number
  label: string
  tier: string
  enabled: boolean
  last_used_at: string | null
  last_429_at: string | null
}

export interface TestConnectionResult {
  ok: boolean
  message: string
  skipped?: boolean
}

export async function listKeys(provider: string): Promise<ProviderKey[]> {
  const { data } = await api.get(`/providers/${encodeURIComponent(provider)}/keys`)
  return data.keys
}

export async function addKey(
  provider: string,
  payload: {
    label: string
    api_key: string
    tier: string
    username?: string
    password?: string
    enabled?: boolean
  },
): Promise<ProviderKey> {
  const { data } = await api.post(`/providers/${encodeURIComponent(provider)}/keys`, payload)
  return data
}

export async function updateKey(
  provider: string,
  id: number,
  payload: Partial<{
    label: string
    api_key: string
    tier: string
    enabled: boolean
    username: string
    password: string
  }>,
): Promise<ProviderKey> {
  const { data } = await api.patch(
    `/providers/${encodeURIComponent(provider)}/keys/${id}`,
    payload,
  )
  return data
}

export async function deleteKey(provider: string, id: number): Promise<void> {
  await api.delete(`/providers/${encodeURIComponent(provider)}/keys/${id}`)
}

export async function testConnection(
  provider: string,
  payload: { api_key: string; username?: string; password?: string },
): Promise<TestConnectionResult> {
  // 400 is a valid "probe failed" signal — don't throw.
  try {
    const { data } = await api.post(
      `/providers/${encodeURIComponent(provider)}/keys/test-connection`,
      payload,
    )
    return data
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: TestConnectionResult } }
    if (axiosErr.response?.data && typeof axiosErr.response.data === 'object') {
      return axiosErr.response.data
    }
    return { ok: false, message: 'Request failed' }
  }
}
