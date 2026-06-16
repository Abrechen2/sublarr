import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDismissedVersion } from '../useDismissedVersion'

const KEY = 'sublarr.update-banner.dismissed'

describe('useDismissedVersion', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('reads an existing dismissed version from localStorage on mount', () => {
    window.localStorage.setItem(KEY, 'v1.2.0')
    const { result } = renderHook(() => useDismissedVersion())
    expect(result.current.dismissedVersion).toBe('v1.2.0')
  })

  it('starts null when nothing is stored', () => {
    const { result } = renderHook(() => useDismissedVersion())
    expect(result.current.dismissedVersion).toBeNull()
  })

  it('dismiss() updates state and persists to localStorage', () => {
    const { result } = renderHook(() => useDismissedVersion())
    act(() => result.current.dismiss('v1.3.0'))
    expect(result.current.dismissedVersion).toBe('v1.3.0')
    expect(window.localStorage.getItem(KEY)).toBe('v1.3.0')
  })
})
