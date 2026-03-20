import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { AutoSaveToast } from '../AutoSaveToast'

describe('AutoSaveToast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    act(() => {
      vi.runAllTimers()
    })
    vi.useRealTimers()
  })

  it('does not render when visible=false', () => {
    act(() => {
      render(<AutoSaveToast visible={false} />)
    })
    expect(screen.queryByTestId('auto-save-toast')).toBeNull()
  })

  it('renders when visible=true', () => {
    act(() => {
      render(<AutoSaveToast visible={true} />)
    })
    expect(screen.getByTestId('auto-save-toast')).toBeInTheDocument()
  })

  it('renders default message text', () => {
    act(() => {
      render(<AutoSaveToast visible={true} />)
    })
    expect(screen.getByTestId('auto-save-toast-message')).toHaveTextContent('Setting saved')
  })

  it('renders custom message when provided', () => {
    act(() => {
      render(<AutoSaveToast visible={true} message="Profile updated" />)
    })
    expect(screen.getByTestId('auto-save-toast-message')).toHaveTextContent('Profile updated')
  })

  it('has role=status and aria-live=polite for accessibility', () => {
    act(() => {
      render(<AutoSaveToast visible={true} />)
    })
    const toast = screen.getByTestId('auto-save-toast')
    expect(toast).toHaveAttribute('role', 'status')
    expect(toast).toHaveAttribute('aria-live', 'polite')
    expect(toast).toHaveAttribute('aria-atomic', 'true')
  })

  it('renders Undo button when onUndo is provided', () => {
    act(() => {
      render(<AutoSaveToast visible={true} onUndo={vi.fn()} />)
    })
    expect(screen.getByTestId('auto-save-toast-undo')).toBeInTheDocument()
  })

  it('does not render Undo button when onUndo is not provided', () => {
    act(() => {
      render(<AutoSaveToast visible={true} />)
    })
    expect(screen.queryByTestId('auto-save-toast-undo')).toBeNull()
  })

  it('calls onUndo when Undo button is clicked', () => {
    const onUndo = vi.fn()
    act(() => {
      render(<AutoSaveToast visible={true} onUndo={onUndo} />)
    })
    fireEvent.click(screen.getByTestId('auto-save-toast-undo'))
    expect(onUndo).toHaveBeenCalledTimes(1)
  })

  it('dismisses after clicking Undo', () => {
    const onUndo = vi.fn()
    act(() => {
      render(<AutoSaveToast visible={true} onUndo={onUndo} />)
    })
    fireEvent.click(screen.getByTestId('auto-save-toast-undo'))
    expect(screen.queryByTestId('auto-save-toast')).toBeNull()
  })

  it('auto-dismisses after 3000ms by default', () => {
    act(() => {
      render(<AutoSaveToast visible={true} />)
    })
    expect(screen.getByTestId('auto-save-toast')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.queryByTestId('auto-save-toast')).toBeNull()
  })

  it('respects custom dismissAfterMs', () => {
    act(() => {
      render(<AutoSaveToast visible={true} dismissAfterMs={5000} />)
    })
    act(() => {
      vi.advanceTimersByTime(4999)
    })
    expect(screen.getByTestId('auto-save-toast')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByTestId('auto-save-toast')).toBeNull()
  })

  it('calls onDismiss when auto-dismissed', () => {
    const onDismiss = vi.fn()
    act(() => {
      render(<AutoSaveToast visible={true} onDismiss={onDismiss} />)
    })
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('renders custom undoLabel when provided', () => {
    act(() => {
      render(<AutoSaveToast visible={true} onUndo={vi.fn()} undoLabel="Revert" />)
    })
    expect(screen.getByTestId('auto-save-toast-undo')).toHaveTextContent('Revert')
  })

  it('renders the success icon', () => {
    act(() => {
      render(<AutoSaveToast visible={true} />)
    })
    expect(screen.getByTestId('auto-save-toast-icon')).toBeInTheDocument()
  })

  it('hides when visible transitions from true to false', () => {
    let rerender!: ReturnType<typeof render>['rerender']
    act(() => {
      const result = render(<AutoSaveToast visible={true} />)
      rerender = result.rerender
    })
    expect(screen.getByTestId('auto-save-toast')).toBeInTheDocument()
    act(() => {
      rerender(<AutoSaveToast visible={false} />)
    })
    expect(screen.queryByTestId('auto-save-toast')).toBeNull()
  })
})
