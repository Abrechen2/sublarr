/**
 * A fresh install lands in the setup wizard.
 *
 * Nothing routed new users to /onboarding: the wizard was reachable only from
 * Settings → General, so a first visit ended on an empty dashboard. Existing
 * installs must never be pushed into it — most of them predate the
 * onboarding_completed flag and only carry setup_wizard_completed.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { shouldOpenOnboarding, markOnboardingRedirected } from '../onboardingRedirect'

const FRESH = { completed: false, has_sonarr: false, has_radarr: false }
const SETUP_OPEN = { wizard_completed: false }

describe('shouldOpenOnboarding', () => {
  beforeEach(() => sessionStorage.clear())

  it('opens the wizard for a fresh install on the dashboard', () => {
    expect(shouldOpenOnboarding(FRESH, SETUP_OPEN, '/')).toBe(true)
  })

  it('waits until both statuses are known', () => {
    expect(shouldOpenOnboarding(undefined, SETUP_OPEN, '/')).toBe(false)
    expect(shouldOpenOnboarding(FRESH, undefined, '/')).toBe(false)
  })

  it('leaves a completed onboarding alone', () => {
    expect(shouldOpenOnboarding({ ...FRESH, completed: true }, SETUP_OPEN, '/')).toBe(false)
  })

  it('leaves an install with Sonarr or Radarr alone', () => {
    expect(shouldOpenOnboarding({ ...FRESH, has_sonarr: true }, SETUP_OPEN, '/')).toBe(false)
    expect(shouldOpenOnboarding({ ...FRESH, has_radarr: true }, SETUP_OPEN, '/')).toBe(false)
  })

  it('leaves an install whose setup wizard already ran alone', () => {
    expect(shouldOpenOnboarding(FRESH, { wizard_completed: true }, '/')).toBe(false)
  })

  it('only redirects from the dashboard, never from a deep link', () => {
    expect(shouldOpenOnboarding(FRESH, SETUP_OPEN, '/settings/general')).toBe(false)
    expect(shouldOpenOnboarding(FRESH, SETUP_OPEN, '/onboarding')).toBe(false)
  })

  it('redirects once per session, so leaving the wizard is respected', () => {
    markOnboardingRedirected()
    expect(shouldOpenOnboarding(FRESH, SETUP_OPEN, '/')).toBe(false)
  })
})
