import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

vi.mock('@/api/client', () => ({
  updateSeriesProcessingConfig: vi.fn().mockResolvedValue(undefined),
}))

import { SeriesProcessingOverride } from '../components/processing/SeriesProcessingOverride'
import { updateSeriesProcessingConfig } from '@/api/client'

test('renders override selects', () => {
  render(<SeriesProcessingOverride seriesId={1} initialConfig={{}} />)
  // Click expand button first since component starts collapsed
  fireEvent.click(screen.getByText('Processing Override'))
  expect(screen.getByText(/HI-Removal/)).toBeTruthy()
  expect(screen.getByText(/Common Fixes/)).toBeTruthy()
})

test('null value shows "Use global"', () => {
  render(<SeriesProcessingOverride seriesId={1} initialConfig={{ hi_removal: null }} />)
  fireEvent.click(screen.getByText('Processing Override'))
  const selects = screen.getAllByRole('combobox')
  expect(selects[0]).toBeTruthy()
})

test('saves config with null for "Use global" option', async () => {
  render(<SeriesProcessingOverride seriesId={42} initialConfig={{ hi_removal: false }} />)
  fireEvent.click(screen.getByText('Processing Override'))

  const saveBtn = screen.getByText('Speichern')
  fireEvent.click(saveBtn)

  await waitFor(() => {
    expect(updateSeriesProcessingConfig).toHaveBeenCalledWith(42, expect.any(Object))
  })
})
