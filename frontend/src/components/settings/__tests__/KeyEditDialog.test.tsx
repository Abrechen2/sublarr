import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import KeyEditDialog from '../KeyEditDialog'

describe('KeyEditDialog', () => {
  test('save button disabled until required fields filled', () => {
    render(
      <KeyEditDialog provider="opensubtitles" onSave={vi.fn()} onCancel={vi.fn()} />,
    )
    expect((screen.getByTestId('save-key') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByTestId('field-api-key'), { target: { value: 'abc' } })
    expect((screen.getByTestId('save-key') as HTMLButtonElement).disabled).toBe(false)
  })

  test('save invokes onSave with payload', () => {
    const onSave = vi.fn()
    render(
      <KeyEditDialog provider="opensubtitles" onSave={onSave} onCancel={vi.fn()} />,
    )
    fireEvent.change(screen.getByTestId('field-api-key'), { target: { value: 'abc' } })
    fireEvent.click(screen.getByTestId('save-key'))
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        label: 'primary',
        api_key: 'abc',
        tier: 'free',
        enabled: true,
      }),
    )
  })

  test('test-connection button disabled until api_key has a value', () => {
    render(
      <KeyEditDialog provider="opensubtitles" onSave={vi.fn()} onCancel={vi.fn()} />,
    )
    expect((screen.getByTestId('test-connection') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByTestId('field-api-key'), { target: { value: 'k' } })
    expect((screen.getByTestId('test-connection') as HTMLButtonElement).disabled).toBe(false)
  })
})
