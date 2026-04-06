import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FormGroup } from '../FormGroup'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

describe('FormGroup', () => {
  it('renders with data-testid="form-group" by default', () => {
    render(
      <FormGroup label="Test Label">
        <input type="text" />
      </FormGroup>,
    )
    expect(screen.getByTestId('form-group')).toBeInTheDocument()
  })

  it('accepts a custom data-testid', () => {
    render(
      <FormGroup label="Test Label" data-testid="custom-group">
        <input type="text" />
      </FormGroup>,
    )
    expect(screen.getByTestId('custom-group')).toBeInTheDocument()
  })

  it('renders the label text', () => {
    render(
      <FormGroup label="API Key">
        <input type="text" />
      </FormGroup>,
    )
    expect(screen.getByTestId('form-group-label')).toHaveTextContent('API Key')
  })

  it('renders hint text when provided', () => {
    render(
      <FormGroup label="Port" hint="Default is 5765">
        <input type="number" />
      </FormGroup>,
    )
    expect(screen.getByTestId('form-group-hint')).toHaveTextContent('Default is 5765')
  })

  it('does not render hint element when hint is omitted', () => {
    render(
      <FormGroup label="Port">
        <input type="number" />
      </FormGroup>,
    )
    expect(screen.queryByTestId('form-group-hint')).toBeNull()
  })

  it('renders a <label> element when htmlFor is provided', () => {
    render(
      <FormGroup label="Language" htmlFor="lang-select">
        <select id="lang-select">
          <option>English</option>
        </select>
      </FormGroup>,
    )
    const labelEl = screen.getByTestId('form-group-label')
    expect(labelEl.tagName).toBe('LABEL')
    expect(labelEl).toHaveAttribute('for', 'lang-select')
  })

  it('renders a <span> element when htmlFor is not provided', () => {
    render(
      <FormGroup label="Status">
        <span>Active</span>
      </FormGroup>,
    )
    const labelEl = screen.getByTestId('form-group-label')
    expect(labelEl.tagName).toBe('SPAN')
  })

  it('renders children inside the control group', () => {
    render(
      <FormGroup label="Token">
        <input data-testid="token-input" type="password" />
      </FormGroup>,
    )
    const control = screen.getByTestId('form-group-control')
    expect(control.contains(screen.getByTestId('token-input'))).toBe(true)
  })

  it('applies additional className to the root element', () => {
    render(
      <FormGroup label="Test" className="custom-class">
        <input type="text" />
      </FormGroup>,
    )
    expect(screen.getByTestId('form-group')).toHaveClass('custom-class')
  })

  it('renders badge and no inline hint when advanced is true', () => {
    render(
      <FormGroup label="My Field" hint="Tooltip text" advanced>
        <input />
      </FormGroup>,
    )
    expect(screen.queryByTestId('form-group-hint')).not.toBeInTheDocument()
    expect(screen.getByTestId('form-group-advanced-badge')).toBeInTheDocument()
    expect(screen.getByTestId('form-group-info-icon')).toBeInTheDocument()
  })

  it('renders no badge when advanced is false (default)', () => {
    render(
      <FormGroup label="My Field" hint="Inline hint">
        <input />
      </FormGroup>,
    )
    expect(screen.getByTestId('form-group-hint')).toBeInTheDocument()
    expect(screen.queryByTestId('form-group-advanced-badge')).not.toBeInTheDocument()
  })

  it('renders nothing for badge/info when advanced is true and no hint provided', () => {
    render(
      <FormGroup label="My Field" advanced>
        <input />
      </FormGroup>,
    )
    expect(screen.queryByTestId('form-group-hint')).not.toBeInTheDocument()
    expect(screen.queryByTestId('form-group-tooltip')).not.toBeInTheDocument()
  })
})
