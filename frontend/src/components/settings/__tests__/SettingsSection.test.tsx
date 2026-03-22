import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SettingsSection } from '../SettingsSection'

describe('SettingsSection', () => {
  it('renders with data-testid="settings-section"', () => {
    render(<SettingsSection title="General">content</SettingsSection>)
    expect(screen.getByTestId('settings-section')).toBeInTheDocument()
  })

  it('renders the section title', () => {
    render(<SettingsSection title="General">content</SettingsSection>)
    expect(screen.getByTestId('settings-section-title')).toHaveTextContent('General')
  })

  it('renders description when provided', () => {
    render(
      <SettingsSection title="General" description="Basic application settings">
        content
      </SettingsSection>,
    )
    expect(screen.getByTestId('settings-section-description')).toHaveTextContent(
      'Basic application settings',
    )
  })

  it('does not render description element when omitted', () => {
    render(<SettingsSection title="General">content</SettingsSection>)
    expect(screen.queryByTestId('settings-section-description')).toBeNull()
  })

  it('renders icon when provided', () => {
    render(
      <SettingsSection title="General" icon={<span data-testid="icon-node">★</span>}>
        content
      </SettingsSection>,
    )
    expect(screen.getByTestId('settings-section-icon')).toBeInTheDocument()
    expect(screen.getByTestId('icon-node')).toBeInTheDocument()
  })

  it('does not render icon wrapper when icon is omitted', () => {
    render(<SettingsSection title="General">content</SettingsSection>)
    expect(screen.queryByTestId('settings-section-icon')).toBeNull()
  })

  it('renders children inside the content area', () => {
    render(
      <SettingsSection title="General">
        <div data-testid="child-node">Child</div>
      </SettingsSection>,
    )
    const content = screen.getByTestId('settings-section-content')
    expect(content.contains(screen.getByTestId('child-node'))).toBe(true)
  })

  it('does not render advanced area when advanced prop is omitted', () => {
    render(<SettingsSection title="General">content</SettingsSection>)
    expect(screen.queryByTestId('settings-section-advanced')).toBeNull()
  })

  it('renders advanced toggle button when advanced prop is provided', () => {
    render(
      <SettingsSection title="General" advanced={<div>Advanced content</div>}>
        content
      </SettingsSection>,
    )
    expect(screen.getByTestId('settings-section-advanced-toggle')).toBeInTheDocument()
  })

  it('advanced content is hidden by default', () => {
    render(
      <SettingsSection title="General" advanced={<div data-testid="adv-content">Advanced</div>}>
        content
      </SettingsSection>,
    )
    expect(screen.queryByTestId('settings-section-advanced-content')).toBeNull()
  })

  it('expands advanced content when toggle is clicked', () => {
    render(
      <SettingsSection title="General" advanced={<div data-testid="adv-content">Advanced</div>}>
        content
      </SettingsSection>,
    )
    const toggle = screen.getByTestId('settings-section-advanced-toggle')
    fireEvent.click(toggle)
    expect(screen.getByTestId('settings-section-advanced-content')).toBeInTheDocument()
    expect(screen.getByTestId('adv-content')).toHaveTextContent('Advanced')
  })

  it('collapses advanced content on second click', () => {
    render(
      <SettingsSection title="General" advanced={<div data-testid="adv-content">Advanced</div>}>
        content
      </SettingsSection>,
    )
    const toggle = screen.getByTestId('settings-section-advanced-toggle')
    fireEvent.click(toggle)
    expect(screen.getByTestId('settings-section-advanced-content')).toBeInTheDocument()
    fireEvent.click(toggle)
    expect(screen.queryByTestId('settings-section-advanced-content')).toBeNull()
  })

  it('toggle button has aria-expanded=false initially', () => {
    render(
      <SettingsSection title="General" advanced={<div>Advanced</div>}>
        content
      </SettingsSection>,
    )
    expect(screen.getByTestId('settings-section-advanced-toggle')).toHaveAttribute(
      'aria-expanded',
      'false',
    )
  })

  it('toggle button has aria-expanded=true after click', () => {
    render(
      <SettingsSection title="General" advanced={<div>Advanced</div>}>
        content
      </SettingsSection>,
    )
    const toggle = screen.getByTestId('settings-section-advanced-toggle')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
  })

  it('applies additional className to root element', () => {
    render(
      <SettingsSection title="General" className="my-class">
        content
      </SettingsSection>,
    )
    expect(screen.getByTestId('settings-section')).toHaveClass('my-class')
  })
})
