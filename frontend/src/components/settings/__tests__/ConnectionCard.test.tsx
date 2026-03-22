import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ConnectionCard } from '../ConnectionCard'
import type { ConnectionCardField } from '../ConnectionCard'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

// ─── Shared fixture ───────────────────────────────────────────────────────────

function makeFields(overrides?: Partial<ConnectionCardField>[]): ConnectionCardField[] {
  const base: ConnectionCardField[] = [
    { key: 'url', label: 'URL', type: 'text', placeholder: 'http://localhost', value: 'http://localhost:8989', onChange: vi.fn() },
    { key: 'api_key', label: 'API Key', type: 'password', value: '', onChange: vi.fn() },
  ]
  if (!overrides) return base
  return base.map((f, i) => ({ ...f, ...(overrides[i] ?? {}) }))
}

function renderCard(props: Partial<React.ComponentProps<typeof ConnectionCard>> = {}) {
  const defaults: React.ComponentProps<typeof ConnectionCard> = {
    abbr: 'SN',
    color: '#5c87ca',
    name: 'Sonarr',
    status: 'unconfigured',
    fields: makeFields(),
    onTest: vi.fn(),
    onSave: vi.fn(),
  }
  return render(<ConnectionCard {...defaults} {...props} />)
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ConnectionCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── Rendering ──

  it('renders with default data-testid="connection-card"', () => {
    renderCard()
    expect(screen.getByTestId('connection-card')).toBeInTheDocument()
  })

  it('accepts a custom data-testid', () => {
    renderCard({ 'data-testid': 'sonarr-connection-card' })
    expect(screen.getByTestId('sonarr-connection-card')).toBeInTheDocument()
  })

  it('renders the service abbreviation', () => {
    renderCard({ abbr: 'RD' })
    expect(screen.getByTestId('connection-card-abbr')).toHaveTextContent('RD')
  })

  it('renders the service name', () => {
    renderCard({ name: 'Radarr' })
    expect(screen.getByTestId('connection-card-name')).toHaveTextContent('Radarr')
  })

  it('renders the status badge', () => {
    renderCard({ status: 'unconfigured' })
    expect(screen.getByTestId('connection-card-status-badge')).toBeInTheDocument()
  })

  it('renders the URL when provided', () => {
    renderCard({ url: 'http://localhost:8989' })
    expect(screen.getByTestId('connection-card-url')).toHaveTextContent('http://localhost:8989')
  })

  it('does not render URL element when url is not provided', () => {
    renderCard({ url: undefined })
    expect(screen.queryByTestId('connection-card-url')).toBeNull()
  })

  it('renders item count when provided', () => {
    renderCard({ itemCount: 42 })
    expect(screen.getByTestId('connection-card-item-count')).toHaveTextContent('42 items')
  })

  it('does not render item count element when itemCount is not provided', () => {
    renderCard({ itemCount: undefined })
    expect(screen.queryByTestId('connection-card-item-count')).toBeNull()
  })

  // ── Status badge variants ──

  it('renders connected status badge', () => {
    renderCard({ status: 'connected' })
    expect(screen.getByTestId('connection-card-status-badge')).toBeInTheDocument()
  })

  it('renders error status badge', () => {
    renderCard({ status: 'error' })
    expect(screen.getByTestId('connection-card-status-badge')).toBeInTheDocument()
  })

  // ── Buttons ──

  it('renders the test button', () => {
    renderCard()
    expect(screen.getByTestId('connection-card-test-btn')).toBeInTheDocument()
  })

  it('renders the edit button', () => {
    renderCard()
    expect(screen.getByTestId('connection-card-edit-btn')).toBeInTheDocument()
  })

  it('calls onTest when test button is clicked', () => {
    const onTest = vi.fn()
    renderCard({ onTest })
    fireEvent.click(screen.getByTestId('connection-card-test-btn'))
    expect(onTest).toHaveBeenCalledTimes(1)
  })

  it('disables test button when isTesting=true', () => {
    renderCard({ isTesting: true })
    expect(screen.getByTestId('connection-card-test-btn')).toBeDisabled()
  })

  // ── Expand/Collapse ──

  it('does not show form by default (collapsed)', () => {
    renderCard()
    expect(screen.queryByTestId('connection-card-form')).toBeNull()
  })

  it('shows form when edit button is clicked', () => {
    renderCard()
    fireEvent.click(screen.getByTestId('connection-card-edit-btn'))
    expect(screen.getByTestId('connection-card-form')).toBeInTheDocument()
  })

  it('collapses form when edit button is clicked again', () => {
    renderCard()
    fireEvent.click(screen.getByTestId('connection-card-edit-btn'))
    expect(screen.getByTestId('connection-card-form')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('connection-card-edit-btn'))
    expect(screen.queryByTestId('connection-card-form')).toBeNull()
  })

  // ── Form fields ──

  it('renders form fields when expanded', () => {
    renderCard()
    fireEvent.click(screen.getByTestId('connection-card-edit-btn'))
    expect(screen.getByTestId('connection-card-field-url')).toBeInTheDocument()
    expect(screen.getByTestId('connection-card-field-api_key')).toBeInTheDocument()
  })

  it('renders password field as type=password by default', () => {
    renderCard()
    fireEvent.click(screen.getByTestId('connection-card-edit-btn'))
    const passwordInput = screen.getByTestId('connection-card-field-api_key')
    expect(passwordInput).toHaveAttribute('type', 'password')
  })

  it('toggles password visibility when eye button is clicked', () => {
    renderCard()
    fireEvent.click(screen.getByTestId('connection-card-edit-btn'))
    const toggleBtn = screen.getByTestId('connection-card-toggle-api_key')
    const passwordInput = screen.getByTestId('connection-card-field-api_key')
    expect(passwordInput).toHaveAttribute('type', 'password')
    fireEvent.click(toggleBtn)
    expect(passwordInput).toHaveAttribute('type', 'text')
    fireEvent.click(toggleBtn)
    expect(passwordInput).toHaveAttribute('type', 'password')
  })

  it('calls onChange when a field value changes', () => {
    const onChange = vi.fn()
    const fields = makeFields([{ key: 'url', label: 'URL', type: 'text', value: '', onChange }])
    renderCard({ fields })
    fireEvent.click(screen.getByTestId('connection-card-edit-btn'))
    fireEvent.change(screen.getByTestId('connection-card-field-url'), { target: { value: 'http://new:8989' } })
    expect(onChange).toHaveBeenCalledWith('http://new:8989')
  })

  // ── Save / Cancel ──

  it('renders save and cancel buttons in expanded form', () => {
    renderCard()
    fireEvent.click(screen.getByTestId('connection-card-edit-btn'))
    expect(screen.getByTestId('connection-card-save-btn')).toBeInTheDocument()
    expect(screen.getByTestId('connection-card-cancel-btn')).toBeInTheDocument()
  })

  it('calls onSave when save button is clicked', () => {
    const onSave = vi.fn()
    renderCard({ onSave })
    fireEvent.click(screen.getByTestId('connection-card-edit-btn'))
    fireEvent.click(screen.getByTestId('connection-card-save-btn'))
    expect(onSave).toHaveBeenCalledTimes(1)
  })

  it('collapses form after save button is clicked', () => {
    renderCard({ onSave: vi.fn() })
    fireEvent.click(screen.getByTestId('connection-card-edit-btn'))
    fireEvent.click(screen.getByTestId('connection-card-save-btn'))
    expect(screen.queryByTestId('connection-card-form')).toBeNull()
  })

  it('collapses form when cancel button is clicked', () => {
    renderCard()
    fireEvent.click(screen.getByTestId('connection-card-edit-btn'))
    fireEvent.click(screen.getByTestId('connection-card-cancel-btn'))
    expect(screen.queryByTestId('connection-card-form')).toBeNull()
  })

  it('disables save button when isSaving=true', () => {
    renderCard({ isSaving: true })
    fireEvent.click(screen.getByTestId('connection-card-edit-btn'))
    expect(screen.getByTestId('connection-card-save-btn')).toBeDisabled()
  })

  // ── Test message ──

  it('renders testMessage when provided', () => {
    renderCard({ testMessage: 'Connection OK' })
    expect(screen.getByTestId('connection-card-test-message')).toHaveTextContent('Connection OK')
  })

  it('does not render testMessage element when testMessage is null', () => {
    renderCard({ testMessage: null })
    expect(screen.queryByTestId('connection-card-test-message')).toBeNull()
  })
})
