/**
 * Episode search/history/interactive/download calls (#226): standalone
 * episodes carry their file path as a `file_path` query parameter so the
 * backend can resolve episodes that have no wanted item yet; Sonarr episodes
 * send no extra parameters.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { get, post } = vi.hoisted(() => ({
  get: vi.fn().mockResolvedValue({ data: {} }),
  post: vi.fn().mockResolvedValue({ data: {} }),
}))

vi.mock('../core', () => ({ api: { get, post } }))

import {
  episodeSearch,
  episodeHistory,
  searchInteractiveEpisode,
  downloadSpecificEpisode,
} from '../library'

const PATH = '/media/my-show/s01e02.mkv'
const PAYLOAD = { provider_name: 'animetosho', subtitle_id: 'x', language: 'de', translate: false }

describe('episode endpoints', () => {
  beforeEach(() => {
    get.mockClear()
    post.mockClear()
  })

  it('episodeSearch sends file_path only when given', async () => {
    await episodeSearch(-1, PATH)
    expect(post).toHaveBeenLastCalledWith('/episodes/-1/search', undefined, {
      params: { file_path: PATH },
    })
    await episodeSearch(101)
    expect(post).toHaveBeenLastCalledWith('/episodes/101/search', undefined, { params: undefined })
  })

  it('episodeHistory sends file_path only when given', async () => {
    await episodeHistory(-1, PATH)
    expect(get).toHaveBeenLastCalledWith('/episodes/-1/history', { params: { file_path: PATH } })
    await episodeHistory(101)
    expect(get).toHaveBeenLastCalledWith('/episodes/101/history', { params: undefined })
  })

  it('searchInteractiveEpisode combines all_providers and file_path', async () => {
    await searchInteractiveEpisode(-1, true, PATH)
    expect(get).toHaveBeenLastCalledWith('/episodes/-1/search-providers', {
      params: { all_providers: true, file_path: PATH },
    })
    await searchInteractiveEpisode(101)
    expect(get).toHaveBeenLastCalledWith('/episodes/101/search-providers', { params: undefined })
  })

  it('downloadSpecificEpisode keeps the payload in the body', async () => {
    await downloadSpecificEpisode(-1, PAYLOAD, PATH)
    expect(post).toHaveBeenLastCalledWith('/episodes/-1/download-specific', PAYLOAD, {
      params: { file_path: PATH },
    })
  })
})
