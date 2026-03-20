import { render, screen, fireEvent } from '@testing-library/react'
import { vi } from 'vitest'

vi.mock('@/api/client', () => ({
  undoProcessSubtitle: vi.fn().mockResolvedValue(undefined),
}))

import { BatchProcessLog } from '../components/processing/BatchProcessLog'

const mockEntries = [
  { filename: 'ep01.de.srt', status: 'ok', changes: 5, backed_up: true, sub_path: '/media/ep01.de.srt' },
  { filename: 'ep02.de.srt', status: 'failed', changes: 0, backed_up: false, sub_path: '/media/ep02.de.srt' },
  { filename: 'ep03.de.srt', status: 'ok', changes: 0, backed_up: false, sub_path: '/media/ep03.de.srt' },
]

test('renders all log entries', () => {
  render(<BatchProcessLog entries={mockEntries} current={3} total={3} />)
  expect(screen.getByText('ep01.de.srt')).toBeTruthy()
  expect(screen.getByText('ep02.de.srt')).toBeTruthy()
})

test('shows undo button only when backed_up is true', () => {
  render(<BatchProcessLog entries={mockEntries} current={3} total={3} />)
  const undoBtns = screen.getAllByText('Undo')
  expect(undoBtns).toHaveLength(1)  // only ep01 has backed_up=true
})

test('calls undo API with correct path', async () => {
  const { undoProcessSubtitle } = await import('@/api/client')
  render(<BatchProcessLog entries={mockEntries} current={3} total={3} />)
  fireEvent.click(screen.getByText('Undo'))
  expect(undoProcessSubtitle).toHaveBeenCalledWith('/media/ep01.de.srt')
})

test('shows progress bar with correct percentage', () => {
  render(<BatchProcessLog entries={mockEntries} current={2} total={4} />)
  expect(screen.getByText('2 / 4')).toBeTruthy()
})
