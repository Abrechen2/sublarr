import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import SeriesOverrideSettings from '../SeriesOverrideSettings'

describe('SeriesOverrideSettings', () => {
  test('save disabled until a field changes', () => {
    render(
      <SeriesOverrideSettings
        seriesId={1}
        initial={{ priority_override: null, min_attempts_per_day: 0 }}
        onSave={vi.fn()}
      />,
    )
    expect((screen.getByTestId('save-override') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByTestId('priority-override-select'), {
      target: { value: 'premium' },
    })
    expect((screen.getByTestId('save-override') as HTMLButtonElement).disabled).toBe(false)
  })

  test('onSave receives current values (priority + min)', () => {
    const onSave = vi.fn()
    render(
      <SeriesOverrideSettings
        seriesId={1}
        initial={{ priority_override: null, min_attempts_per_day: 0 }}
        onSave={onSave}
      />,
    )
    fireEvent.change(screen.getByTestId('priority-override-select'), {
      target: { value: 'premium' },
    })
    fireEvent.change(screen.getByTestId('min-attempts-input'), {
      target: { value: '5' },
    })
    fireEvent.click(screen.getByTestId('save-override'))
    expect(onSave).toHaveBeenCalledWith({
      priority_override: 'premium',
      min_attempts_per_day: 5,
      subtitle_format_requirement: null,
    })
  })

  test('inherit option maps to null priority_override', () => {
    const onSave = vi.fn()
    render(
      <SeriesOverrideSettings
        seriesId={1}
        initial={{ priority_override: 'premium', min_attempts_per_day: 0 }}
        onSave={onSave}
      />,
    )
    fireEvent.change(screen.getByTestId('priority-override-select'), {
      target: { value: '' },
    })
    fireEvent.click(screen.getByTestId('save-override'))
    expect(onSave).toHaveBeenCalledWith({
      priority_override: null,
      min_attempts_per_day: 0,
      subtitle_format_requirement: null,
    })
  })

  test('min-attempts clamped to [0, 50]', () => {
    const onSave = vi.fn()
    render(
      <SeriesOverrideSettings
        seriesId={1}
        initial={{ priority_override: null, min_attempts_per_day: 0 }}
        onSave={onSave}
      />,
    )
    fireEvent.change(screen.getByTestId('min-attempts-input'), {
      target: { value: '999' },
    })
    fireEvent.click(screen.getByTestId('save-override'))
    expect(onSave).toHaveBeenCalledWith({
      priority_override: null,
      min_attempts_per_day: 50,
      subtitle_format_requirement: null,
    })
  })
  test('format requirement select maps to subtitle_format_requirement', () => {
    const onSave = vi.fn()
    render(
      <SeriesOverrideSettings
        seriesId={1}
        initial={{ priority_override: null, min_attempts_per_day: 0 }}
        onSave={onSave}
      />,
    )
    fireEvent.change(screen.getByTestId('format-requirement-select'), {
      target: { value: 'require_ass' },
    })
    fireEvent.click(screen.getByTestId('save-override'))
    expect(onSave).toHaveBeenCalledWith({
      priority_override: null,
      min_attempts_per_day: 0,
      subtitle_format_requirement: 'require_ass',
    })
  })
})
