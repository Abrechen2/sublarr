/** Decides when a first visit is sent to the setup wizard at /onboarding.
 *
 *  Only a fresh install qualifies: onboarding not completed, neither Sonarr
 *  nor Radarr connected, and the setup wizard (scheduler profile) not run.
 *  Installs from before the onboarding_completed flag carry only
 *  setup_wizard_completed, so that check keeps them out. The redirect fires
 *  once per browser session and only from the dashboard, so leaving the
 *  wizard or opening a deep link is respected. */

const REDIRECTED_KEY = 'sublarr_onboarding_redirected'

interface OnboardingStatus {
  completed: boolean
  has_sonarr: boolean
  has_radarr: boolean
}

interface SetupStatus {
  wizard_completed: boolean
}

function alreadyRedirected(): boolean {
  try {
    return sessionStorage.getItem(REDIRECTED_KEY) !== null
  } catch {
    return false
  }
}

export function markOnboardingRedirected(): void {
  try {
    sessionStorage.setItem(REDIRECTED_KEY, '1')
  } catch {
    // Storage blocked: the redirect may repeat once per page load, which is harmless.
  }
}

export function shouldOpenOnboarding(
  onboarding: OnboardingStatus | undefined,
  setup: SetupStatus | undefined,
  pathname: string,
): boolean {
  if (!onboarding || !setup) return false
  if (pathname !== '/') return false
  if (onboarding.completed || onboarding.has_sonarr || onboarding.has_radarr) return false
  if (setup.wizard_completed) return false
  return !alreadyRedirected()
}
