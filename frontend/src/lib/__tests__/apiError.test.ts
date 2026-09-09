import { describe, it, expect } from 'vitest'

import { apiErrorMessage } from '../apiError'

describe('apiErrorMessage', () => {
  it('returns the API error field — the 409 case from forgejo #20', () => {
    const error = {
      response: { status: 409, data: { error: 'A profile named "Anime DE" already exists' } },
    }
    expect(apiErrorMessage(error, 'save failed')).toBe('A profile named "Anime DE" already exists')
  })

  it('accepts message and detail as well', () => {
    expect(apiErrorMessage({ response: { data: { message: 'nope' } } }, 'fb')).toBe('nope')
    expect(apiErrorMessage({ response: { data: { detail: 'nope' } } }, 'fb')).toBe('nope')
  })

  it('accepts a plain string body', () => {
    expect(apiErrorMessage({ response: { data: '  boom  ' } }, 'fb')).toBe('boom')
  })

  it('falls back when the request never reached the API', () => {
    expect(apiErrorMessage(new Error('Network Error'), 'fb')).toBe('fb')
    expect(apiErrorMessage(undefined, 'fb')).toBe('fb')
    expect(apiErrorMessage(null, 'fb')).toBe('fb')
  })

  it('falls back on an empty or missing error field rather than showing blank', () => {
    expect(apiErrorMessage({ response: { data: { error: '   ' } } }, 'fb')).toBe('fb')
    expect(apiErrorMessage({ response: { data: { other: 'x' } } }, 'fb')).toBe('fb')
    expect(apiErrorMessage({ response: {} }, 'fb')).toBe('fb')
  })
})
