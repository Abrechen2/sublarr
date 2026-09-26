import { describe, it, expect } from 'vitest'
import de from '@/i18n/locales/de/settings.json'
import en from '@/i18n/locales/en/settings.json'
import { actionTypeLabel } from '../actionTypeLabel'

type Dict = Record<string, unknown>

function lookup(dict: Dict, key: string): string | undefined {
  const value = key.split('.').reduce<unknown>((node, part) => (node as Dict | undefined)?.[part], dict)
  return typeof value === 'string' ? value : undefined
}

function tFor(dict: Dict) {
  return (key: string, opts?: { defaultValue?: string }) => lookup(dict, key) ?? opts?.defaultValue ?? key
}

describe('actionTypeLabel', () => {
  it('labels the foreign-track sweep history rows in German and English', () => {
    expect(actionTypeLabel(tFor(de as Dict), 'scheduled_foreign_track_sweep')).toBe('Spur-Bereinigung (Sweep)')
    expect(actionTypeLabel(tFor(en as Dict), 'scheduled_foreign_track_sweep')).toBe('Track cleanup (sweep)')
  })

  it('falls back to the raw action type when no label exists', () => {
    expect(actionTypeLabel(tFor(de as Dict), 'some_unknown_action')).toBe('some_unknown_action')
  })
})
