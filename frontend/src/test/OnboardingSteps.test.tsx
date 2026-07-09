import { describe, it, expect } from 'vitest'
import { ALL_STEPS, getVisibleSteps } from '../pages/Onboarding'

describe('Onboarding step structure', () => {
  it('ALL_STEPS contains language step', () => {
    expect(ALL_STEPS.map(s => s.id)).toContain('language')
  })

  it('ALL_STEPS contains automation step', () => {
    expect(ALL_STEPS.map(s => s.id)).toContain('automation')
  })

  it('arr mode includes language and automation steps', () => {
    const ids = getVisibleSteps('arr').map(s => s.id)
    expect(ids).toContain('language')
    expect(ids).toContain('automation')
  })

  it('standalone mode includes language and automation steps', () => {
    const ids = getVisibleSteps('standalone').map(s => s.id)
    expect(ids).toContain('language')
    expect(ids).toContain('automation')
  })

  it('language step is between pathmapping and providers in arr mode', () => {
    const ids = getVisibleSteps('arr').map(s => s.id)
    expect(ids.indexOf('language')).toBeGreaterThan(ids.indexOf('pathmapping'))
    expect(ids.indexOf('language')).toBeLessThan(ids.indexOf('providers'))
  })

  it('automation step is between providers and ollama in arr mode', () => {
    const ids = getVisibleSteps('arr').map(s => s.id)
    expect(ids.indexOf('automation')).toBeGreaterThan(ids.indexOf('providers'))
    expect(ids.indexOf('automation')).toBeLessThan(ids.indexOf('ollama'))
  })
})
