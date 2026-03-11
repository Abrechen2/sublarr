import { describe, it, expect } from 'vitest'
import { act } from '@testing-library/react'
import { render } from '@testing-library/react'
import { ToastContainer, toast } from '@/components/shared/Toast'

describe('ToastContainer', () => {
  it('renders a region with role=status and aria-live=polite when a toast fires', async () => {
    const { getByRole } = render(<ToastContainer />)
    await act(async () => {
      toast('Hello world', 'success')
    })
    const statusEl = getByRole('status')
    expect(statusEl).toHaveAttribute('aria-live', 'polite')
    expect(statusEl).toHaveAttribute('aria-atomic', 'true')
  })
})
