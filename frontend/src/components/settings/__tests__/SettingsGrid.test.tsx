import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { SettingsGrid } from '../SettingsGrid'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('SettingsGrid', () => {
  it('renders all 8 category cards', () => {
    renderWithRouter(<SettingsGrid />)
    const cards = screen.getAllByRole('button').filter(
      (el) => el.getAttribute('data-testid')?.match(/^settings-card-[^-]+$/)
    )
    expect(cards).toHaveLength(8)
  })

  it('renders each card with an icon box', () => {
    renderWithRouter(<SettingsGrid />)
    const iconBoxes = screen.getAllByTestId(/^settings-card-icon-/)
    expect(iconBoxes).toHaveLength(8)
  })

  it('renders the General card with title and description', () => {
    renderWithRouter(<SettingsGrid />)
    expect(screen.getByTestId('settings-card-general')).toBeInTheDocument()
    expect(screen.getByTestId('settings-card-title-general')).toBeInTheDocument()
    expect(screen.getByTestId('settings-card-desc-general')).toBeInTheDocument()
  })

  it('renders the Connections card', () => {
    renderWithRouter(<SettingsGrid />)
    expect(screen.getByTestId('settings-card-connections')).toBeInTheDocument()
  })

  it('renders the Subtitles card', () => {
    renderWithRouter(<SettingsGrid />)
    expect(screen.getByTestId('settings-card-subtitles')).toBeInTheDocument()
  })

  it('renders the Providers card', () => {
    renderWithRouter(<SettingsGrid />)
    expect(screen.getByTestId('settings-card-providers')).toBeInTheDocument()
  })

  it('renders the Automation card', () => {
    renderWithRouter(<SettingsGrid />)
    expect(screen.getByTestId('settings-card-automation')).toBeInTheDocument()
  })

  it('renders the Translation card', () => {
    renderWithRouter(<SettingsGrid />)
    expect(screen.getByTestId('settings-card-translation')).toBeInTheDocument()
  })

  it('renders the Notifications card', () => {
    renderWithRouter(<SettingsGrid />)
    expect(screen.getByTestId('settings-card-notifications')).toBeInTheDocument()
  })

  it('renders the System card', () => {
    renderWithRouter(<SettingsGrid />)
    expect(screen.getByTestId('settings-card-system')).toBeInTheDocument()
  })

  it('renders a count or tag element on each card', () => {
    renderWithRouter(<SettingsGrid />)
    const badges = screen.getAllByTestId(/^settings-card-badge-/)
    expect(badges).toHaveLength(8)
  })

  it('navigates to /settings/general when General card is clicked', async () => {
    const user = userEvent.setup()
    renderWithRouter(<SettingsGrid />)
    await user.click(screen.getByTestId('settings-card-general'))
    expect(mockNavigate).toHaveBeenCalledWith('/settings/general')
  })

  it('navigates to /settings/providers when Providers card is clicked', async () => {
    const user = userEvent.setup()
    renderWithRouter(<SettingsGrid />)
    await user.click(screen.getByTestId('settings-card-providers'))
    expect(mockNavigate).toHaveBeenCalledWith('/settings/providers')
  })

  it('navigates to /settings/system when System card is clicked', async () => {
    const user = userEvent.setup()
    renderWithRouter(<SettingsGrid />)
    await user.click(screen.getByTestId('settings-card-system'))
    expect(mockNavigate).toHaveBeenCalledWith('/settings/system')
  })

  it('does not navigate when a disabled card is clicked', async () => {
    mockNavigate.mockClear()
    const user = userEvent.setup()
    renderWithRouter(<SettingsGrid disabledCategories={['general']} />)
    const card = screen.getByTestId('settings-card-general')
    // disabled cards have pointer-events: none via CSS, but we verify the navigate is not called
    await user.click(card)
    expect(mockNavigate).not.toHaveBeenCalledWith('/settings/general')
  })

  it('applies disabled styling to disabled cards', () => {
    renderWithRouter(<SettingsGrid disabledCategories={['general']} />)
    const card = screen.getByTestId('settings-card-general')
    expect(card).toHaveAttribute('data-disabled', 'true')
  })
})
