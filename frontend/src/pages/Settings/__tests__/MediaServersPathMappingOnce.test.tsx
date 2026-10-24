/**
 * A media server shows its path mapping once.
 *
 * Every backend lists path_mapping in its config_fields, and the tab renders
 * its own translated Path Mapping row as well, so the form showed the field
 * twice, both bound to the same value.
 */
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'
import { MediaServersTab } from '../MediaServersTab'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

const PLEX = {
  name: 'plex',
  display_name: 'Plex',
  config_fields: [
    { key: 'url', label: 'Server URL', type: 'text', required: true, default: '' },
    { key: 'token', label: 'Plex Token', type: 'password', required: true, default: '' },
    { key: 'path_mapping', label: 'Path Mapping', type: 'text', required: false, default: '' },
  ],
}

// Stable references: the tab copies the instances into state in an effect.
const TYPES = { data: [PLEX], isLoading: false }
const INSTANCES = {
  data: [{ type: 'plex', name: 'Living room', enabled: true, url: 'http://plex:32400', path_mapping: '/media:/data' }],
  isLoading: false,
}

vi.mock('@/hooks/useApi', () => ({
  useMediaServerTypes: () => TYPES,
  useMediaServerInstances: () => INSTANCES,
  useSaveMediaServerInstances: () => ({ mutate: vi.fn(), isPending: false }),
  useTestMediaServer: () => ({ mutate: vi.fn(), isPending: false }),
}))

describe('MediaServersTab path mapping', () => {
  it('renders the path mapping field once', () => {
    render(
      <AdvancedSettingsProvider>
        <MediaServersTab />
      </AdvancedSettingsProvider>,
    )
    fireEvent.click(screen.getByText('Living room'))

    expect(screen.getAllByDisplayValue('/media:/data')).toHaveLength(1)
    expect(screen.queryByText('Path Mapping')).toBeNull()
    expect(screen.getByText('media_servers.field_path_mapping')).toBeTruthy()
    expect(screen.getByDisplayValue('http://plex:32400')).toBeTruthy()
  })
})
