/**
 * Series NFO export must call the series route. It used to POST
 * `{series_id}` to the single-file `/subtitles/export-nfo`, which needs a
 * `?path=` query and answered 400 in every mode.
 */
import { describe, it, expect, vi } from 'vitest'

const { post } = vi.hoisted(() => ({
  post: vi.fn().mockResolvedValue({ data: { status: 'ok', exported: 2, skipped: 0 } }),
}))

vi.mock('../core', () => ({ api: { post } }))

import { exportSeriesNfo } from '../library'

describe('exportSeriesNfo', () => {
  it('posts to the series export route and returns the counts', async () => {
    const res = await exportSeriesNfo(7)
    expect(post).toHaveBeenCalledWith('/series/7/subtitles/export-nfo')
    expect(res.exported).toBe(2)
  })
})
