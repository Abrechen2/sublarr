/**
 * Provider credential fields save once, when the user leaves the field.
 *
 * They used to save per keystroke. The refetch after the first save returned
 * the secret masked as ***configured***, the input emptied, and the next
 * letter began a new password — so a typed password was stored as one
 * character. Prod 1.17.0-rc.11: the OpenSubtitles VIP login never held.
 */
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'
import type { ProviderInfo } from '@/lib/types'
import { ProviderEditor } from '../ProviderEditor'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))
vi.mock('@/api/providerKeys', () => ({
  listKeys: vi.fn().mockResolvedValue([]),
  addKey: vi.fn(),
  updateKey: vi.fn(),
  deleteKey: vi.fn(),
}))
vi.mock('@/components/settings/ProviderKeysPool', () => ({
  default: () => null,
  KEY_PROVIDERS: [] as const,
}))
vi.mock('../ProviderLanguageExcludes', () => ({
  ProviderLanguageExcludes: () => null,
}))

const PROVIDER = {
  name: 'opensubtitles',
  display_name: 'OpenSubtitles',
  enabled: true,
  config_fields: [
    { key: 'opensubtitles_password', label: 'Password', type: 'password', required: false },
  ],
  languages: [],
} as unknown as ProviderInfo

function editor(fieldValues: Record<string, string>, onFieldChange: (k: string, v: string) => void) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <AdvancedSettingsProvider>
        <ProviderEditor
          provider={PROVIDER}
          cacheCount={0}
          fieldValues={fieldValues}
          onFieldChange={onFieldChange}
          onTest={vi.fn()}
          onToggle={vi.fn()}
          onClearCache={vi.fn()}
          onReEnable={vi.fn()}
        />
      </AdvancedSettingsProvider>
    </QueryClientProvider>
  )
}

const input = () => screen.getByLabelText('Password') as HTMLInputElement

describe('ProviderEditor — credential fields save on blur', () => {
  it('saves the whole value once, even when the server masks it mid-typing', () => {
    const onFieldChange = vi.fn()
    const { rerender } = render(editor({ opensubtitles_password: '' }, onFieldChange))

    fireEvent.change(input(), { target: { value: 's' } })
    // What a refetch after a per-keystroke save delivered.
    rerender(editor({ opensubtitles_password: '***configured***' }, onFieldChange))
    fireEvent.change(input(), { target: { value: 'secret' } })
    expect(input().value).toBe('secret')
    expect(onFieldChange).not.toHaveBeenCalled()

    fireEvent.blur(input())
    expect(onFieldChange).toHaveBeenCalledTimes(1)
    expect(onFieldChange).toHaveBeenCalledWith('opensubtitles_password', 'secret')
  })

  it('saves on Enter', () => {
    const onFieldChange = vi.fn()
    render(editor({ opensubtitles_password: '' }, onFieldChange))
    fireEvent.change(input(), { target: { value: 'secret' } })
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(onFieldChange).toHaveBeenCalledWith('opensubtitles_password', 'secret')
  })

  it('does not save a field the user only visited', () => {
    const onFieldChange = vi.fn()
    render(editor({ opensubtitles_password: '***configured***' }, onFieldChange))
    fireEvent.focus(input())
    fireEvent.blur(input())
    expect(onFieldChange).not.toHaveBeenCalled()
  })

  it('does not wipe a stored secret when the user types and deletes again', () => {
    const onFieldChange = vi.fn()
    render(editor({ opensubtitles_password: '***configured***' }, onFieldChange))
    fireEvent.change(input(), { target: { value: 'x' } })
    fireEvent.change(input(), { target: { value: '' } })
    fireEvent.blur(input())
    expect(onFieldChange).not.toHaveBeenCalled()
  })
})
