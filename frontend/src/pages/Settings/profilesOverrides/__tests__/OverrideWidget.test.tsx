import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { OverrideWidget } from '../OverrideWidget'
import type { InheritanceField } from '../inheritanceFields'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, fb?: string) => fb ?? k }),
}))

const boolField: InheritanceField = {
  key: 'cleanup_foreign_tracks', type: 'boolean',
  labelKey: 'profiles_overrides.field.cleanup_foreign_tracks',
}
const enumField: InheritanceField = {
  key: 'hi_preference', type: 'enum',
  labelKey: 'profiles_overrides.field.hi_preference',
  options: ['include', 'prefer', 'exclude', 'only'],
}
const intField: InheritanceField = {
  key: 'min_attempts_per_day', type: 'integer',
  labelKey: 'profiles_overrides.field.min_attempts_per_day',
}

describe('OverrideWidget', () => {
  it('renders TriStateToggle for boolean field', () => {
    render(<OverrideWidget field={boolField} value={null} onChange={() => {}} />)
    expect(screen.getByTestId('tri-state-toggle')).toBeInTheDocument()
  })

  it('renders Select for enum field', () => {
    render(<OverrideWidget field={enumField} value={null} onChange={() => {}} />)
    expect(screen.getByRole('combobox')).toBeInTheDocument()
  })

  it('emits null when enum select set to inherit option', () => {
    const onChange = vi.fn()
    render(<OverrideWidget field={enumField} value="prefer" onChange={onChange} />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '' } })
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('renders number input for integer field', () => {
    render(<OverrideWidget field={intField} value={null} onChange={() => {}} />)
    expect(screen.getByRole('spinbutton')).toBeInTheDocument()
  })

  it('integer reset button emits null', () => {
    const onChange = vi.fn()
    render(<OverrideWidget field={intField} value={3} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /inherit/i }))
    expect(onChange).toHaveBeenCalledWith(null)
  })
})
