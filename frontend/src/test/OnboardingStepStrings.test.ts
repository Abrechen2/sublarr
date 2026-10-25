/**
 * Every onboarding step has a title and description in both languages.
 *
 * The Language and Automation steps referenced keys that existed in neither
 * locale, so the wizard showed the raw key as the step heading.
 */
import { describe, expect, it } from 'vitest'
import { ALL_STEPS } from '@/pages/Onboarding'
import en from '@/i18n/locales/en/onboarding.json'
import de from '@/i18n/locales/de/onboarding.json'

function lookup(bundle: Record<string, unknown>, key: string): unknown {
  return key.split('.').reduce<unknown>(
    (node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined),
    bundle,
  )
}

describe.each([
  ['en', en],
  ['de', de],
])('onboarding step strings (%s)', (_lang, bundle) => {
  it.each(ALL_STEPS.map((s) => [s.id, s.titleKey, s.descKey]))(
    '%s has a title and a description',
    (_id, titleKey, descKey) => {
      expect(typeof lookup(bundle, titleKey)).toBe('string')
      expect(typeof lookup(bundle, descKey)).toBe('string')
    },
  )
})
