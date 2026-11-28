/**
 * Sonarr/Radarr exclusion fields (Forgejo #83).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ArrExclusionsFields } from '../ArrExclusionsFields'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const save = vi.fn()

function renderFields(config: Record<string, unknown>) {
  return render(
    <AdvancedSettingsProvider>
      <ArrExclusionsFields config={config} save={save} disabled={false} />
    </AdvancedSettingsProvider>,
  )
}

describe('ArrExclusionsFields', () => {
  beforeEach(() => save.mockClear())

  it('saves the tag list normalised on blur, not on every keystroke', () => {
    renderFields({ sonarr_exclude_tags: '' })
    const input = screen.getByTestId('input-sonarr-exclude-tags')

    fireEvent.change(input, { target: { value: ' No-Subs ,kids,, ' } })
    expect(save).not.toHaveBeenCalled()
    fireEvent.blur(input)

    expect(save).toHaveBeenCalledWith({ sonarr_exclude_tags: 'no-subs, kids' })
  })

  it('does not save an unchanged tag list', () => {
    renderFields({ radarr_exclude_tags: 'no-subs' })
    fireEvent.blur(screen.getByTestId('input-radarr-exclude-tags'))

    expect(save).not.toHaveBeenCalled()
  })

  it('adds and removes series types in a stable order', () => {
    renderFields({ sonarr_exclude_series_types: 'daily' })

    expect(screen.getByTestId('checkbox-exclude-series-type-daily')).toBeChecked()
    fireEvent.click(screen.getByTestId('checkbox-exclude-series-type-anime'))
    expect(save).toHaveBeenLastCalledWith({ sonarr_exclude_series_types: 'anime,daily' })

    fireEvent.click(screen.getByTestId('checkbox-exclude-series-type-daily'))
    expect(save).toHaveBeenLastCalledWith({ sonarr_exclude_series_types: '' })
  })

  it('shows everything off by default', () => {
    renderFields({})

    for (const type of ['standard', 'anime', 'daily']) {
      expect(screen.getByTestId(`checkbox-exclude-series-type-${type}`)).not.toBeChecked()
    }
    expect(screen.getByTestId('input-sonarr-exclude-tags')).toHaveValue('')
  })
})
