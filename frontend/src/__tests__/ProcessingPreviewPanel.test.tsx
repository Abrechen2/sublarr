// frontend/src/__tests__/ProcessingPreviewPanel.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { vi } from 'vitest'
import { ProcessingPreviewPanel } from '../components/processing/ProcessingPreviewPanel'

const mockChanges = [
  { event_index: 0, timestamp: '00:00:01,000 --> 00:00:02,000', original_text: '[MUSIC PLAYING]', modified_text: '', mod_name: 'hi_removal' },
  { event_index: 1, timestamp: '00:00:03,000 --> 00:00:04,000', original_text: 'JOHN: Hello', modified_text: 'Hello', mod_name: 'hi_removal' },
]

test('renders change count', () => {
  render(
    <ProcessingPreviewPanel
      changes={mockChanges}
      onConfirm={vi.fn()}
      onCancel={vi.fn()}
    />
  )
  expect(screen.getByText(/2 Änderungen/)).toBeTruthy()
})

test('shows original and modified text', () => {
  render(
    <ProcessingPreviewPanel
      changes={mockChanges}
      onConfirm={vi.fn()}
      onCancel={vi.fn()}
    />
  )
  expect(screen.getByText('[MUSIC PLAYING]')).toBeTruthy()
  expect(screen.getByText('JOHN: Hello')).toBeTruthy()
})

test('calls onConfirm when Übernehmen clicked', () => {
  const onConfirm = vi.fn()
  render(
    <ProcessingPreviewPanel
      changes={mockChanges}
      onConfirm={onConfirm}
      onCancel={vi.fn()}
    />
  )
  fireEvent.click(screen.getByText('Übernehmen'))
  expect(onConfirm).toHaveBeenCalledOnce()
})

test('calls onCancel without modifying when Abbrechen clicked', () => {
  const onCancel = vi.fn()
  const onConfirm = vi.fn()
  render(
    <ProcessingPreviewPanel
      changes={mockChanges}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  )
  fireEvent.click(screen.getByText('Abbrechen'))
  expect(onCancel).toHaveBeenCalledOnce()
  expect(onConfirm).not.toHaveBeenCalled()
})
