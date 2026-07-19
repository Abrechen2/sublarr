import { describe, it, expect } from 'vitest'

import { findAdjacentMarker } from '../waveformNavigation'

describe('findAdjacentMarker', () => {
  const markers = [1, 3.5, 3.5, 7, 10] // includes a duplicate on purpose

  it('finds the nearest marker after the current time', () => {
    expect(findAdjacentMarker(markers, 4, 'next')).toBe(7)
  })

  it('finds the nearest marker before the current time', () => {
    expect(findAdjacentMarker(markers, 4, 'prev')).toBe(3.5)
  })

  it('skips a marker exactly at the current time (strict) so presses advance', () => {
    expect(findAdjacentMarker(markers, 3.5, 'next')).toBe(7)
    expect(findAdjacentMarker(markers, 3.5, 'prev')).toBe(1)
  })

  it('returns null when there is nothing after the last marker', () => {
    expect(findAdjacentMarker(markers, 10, 'next')).toBeNull()
    expect(findAdjacentMarker(markers, 99, 'next')).toBeNull()
  })

  it('returns null when there is nothing before the first marker', () => {
    expect(findAdjacentMarker(markers, 1, 'prev')).toBeNull()
    expect(findAdjacentMarker(markers, 0, 'prev')).toBeNull()
  })

  it('works on an unsorted input', () => {
    expect(findAdjacentMarker([10, 1, 7, 3.5], 4, 'next')).toBe(7)
    expect(findAdjacentMarker([10, 1, 7, 3.5], 4, 'prev')).toBe(3.5)
  })

  it('ignores non-finite entries', () => {
    expect(findAdjacentMarker([NaN, 2, Infinity, 5], 3, 'next')).toBe(5)
    expect(findAdjacentMarker([NaN, 2, Infinity, 5], 3, 'prev')).toBe(2)
  })

  it('returns null for an empty marker list', () => {
    expect(findAdjacentMarker([], 4, 'next')).toBeNull()
    expect(findAdjacentMarker([], 4, 'prev')).toBeNull()
  })
})
