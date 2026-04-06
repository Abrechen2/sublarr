import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LanguagePillSelector } from '../LanguagePillSelector'

const LANGUAGES = [
  { value: 'de', label: 'Deutsch' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: 'Japanese' },
]

describe('LanguagePillSelector', () => {
  it('renders current selections as pills', () => {
    render(<LanguagePillSelector value={['de', 'en']} options={LANGUAGES} onChange={vi.fn()} />)
    expect(screen.getByText('Deutsch')).toBeInTheDocument()
    expect(screen.getByText('English')).toBeInTheDocument()
  })

  it('calls onChange with new value when a language is removed', () => {
    const onChange = vi.fn()
    render(<LanguagePillSelector value={['de', 'en']} options={LANGUAGES} onChange={onChange} />)
    fireEvent.click(screen.getAllByLabelText('Remove')[0])
    expect(onChange).toHaveBeenCalledWith(['en'])
  })

  it('calls onChange with added value when a language is selected from dropdown', () => {
    const onChange = vi.fn()
    render(<LanguagePillSelector value={['de']} options={LANGUAGES} onChange={onChange} />)
    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: 'ja' } })
    expect(onChange).toHaveBeenCalledWith(['de', 'ja'])
  })

  it('does not show already-selected languages in the dropdown', () => {
    render(<LanguagePillSelector value={['de', 'en']} options={LANGUAGES} onChange={vi.fn()} />)
    const options = screen.getAllByRole('option')
    const optionValues = options.map((o) => o.getAttribute('value'))
    expect(optionValues).not.toContain('de')
    expect(optionValues).not.toContain('en')
    expect(optionValues).toContain('ja')
  })
})
