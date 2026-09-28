/**
 * #213 — say it when the Settings credential field is not the one searches use.
 *
 * Once `provider_account_pools` has a row, `_provider_credentials_configured`
 * treats the pool as the only source: "Pool rows, once they exist, stay the
 * only source: an exhausted or cooling pool is not bypassed by a Settings
 * value." The Settings field still accepts input and still reports a
 * successful save — it just has no effect on searching.
 *
 * The reporter rotated a Jimaku key that way, watched the save succeed and the
 * masked value change, and spent about an hour treating the 401s that followed
 * as a dead key. Nothing in the UI or the log connected the two places.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'
import type { ProviderInfo } from '@/lib/types'
import { ProviderEditor } from '../ProviderEditor'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'count' in opts ? `${key}:${opts.count}` : key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

const listKeys = vi.hoisted(() => vi.fn())
vi.mock('@/api/providerKeys', () => ({
  listKeys,
  addKey: vi.fn(),
  updateKey: vi.fn(),
  deleteKey: vi.fn(),
}))

// The pool component itself is not under test here and pulls in dialogs.
vi.mock('@/components/settings/ProviderKeysPool', () => ({
  default: () => <div data-testid="pool" />,
  KEY_PROVIDERS: ['opensubtitles', 'subdl', 'jimaku'] as const,
}))
vi.mock('../ProviderLanguageExcludes', () => ({
  ProviderLanguageExcludes: () => null,
}))

function provider(name: string): ProviderInfo {
  return {
    name,
    display_name: name,
    enabled: true,
    config_fields: [{ key: `${name}_api_key`, label: 'API key', type: 'password', required: true }],
    languages: [],
  } as unknown as ProviderInfo
}

function renderEditor(name = 'jimaku') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <AdvancedSettingsProvider>
        <ProviderEditor
        provider={provider(name)}
        cacheCount={0}
        fieldValues={{}}
        onFieldChange={vi.fn()}
        onTest={vi.fn()}
        onProbe={vi.fn()}
        onSave={vi.fn()}
        onDelete={vi.fn()}
        onClearCache={vi.fn()}
        />
      </AdvancedSettingsProvider>
    </QueryClientProvider>,
  )
}

describe('ProviderEditor — pool note (#213)', () => {
  beforeEach(() => {
    listKeys.mockReset()
  })

  it('says the field is unused once the pool holds a key', async () => {
    listKeys.mockResolvedValue([{ id: 1, label: 'k1' }])
    renderEditor()
    const note = await screen.findByTestId('pool-overrides-jimaku_api_key')
    expect(note.textContent).toContain('pool_overrides_field')
  })

  it('carries the key count, so two keys read differently from one', async () => {
    listKeys.mockResolvedValue([{ id: 1 }, { id: 2 }])
    renderEditor()
    const note = await screen.findByTestId('pool-overrides-jimaku_api_key')
    expect(note.textContent).toContain(':2')
  })

  it('stays quiet while the pool is empty — then the field IS the source', async () => {
    listKeys.mockResolvedValue([])
    renderEditor()
    await waitFor(() => expect(listKeys).toHaveBeenCalled())
    expect(screen.queryByTestId('pool-overrides-jimaku_api_key')).toBeNull()
  })

  it('does not ask about a pool for a provider that has none', async () => {
    listKeys.mockResolvedValue([{ id: 1 }])
    renderEditor('gestdown')
    await waitFor(() => expect(screen.getByTestId('pool')).toBeTruthy())
    expect(listKeys).not.toHaveBeenCalled()
    expect(screen.queryByTestId('pool-overrides-gestdown_api_key')).toBeNull()
  })
})
