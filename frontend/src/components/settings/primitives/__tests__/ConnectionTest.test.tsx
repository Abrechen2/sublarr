/**
 * ConnectionTest — state-machine smoke tests.
 *
 * Verifies the idle → testing → (ok | fail) → idle-on-re-click flow and
 * ensures the onResult callback fires in every terminal state (including
 * thrown exceptions, which coerce to fail).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ConnectionTest } from '../ConnectionTest'
import type { ConnectionTestResult } from '../ConnectionTest'

describe('ConnectionTest', () => {
  it('starts in idle state, no pill visible', () => {
    render(<ConnectionTest label="Test" onTest={() => Promise.resolve({ ok: true })} />)
    const root = screen.getByTestId('connection-test')
    expect(root.getAttribute('data-state')).toBe('idle')
    expect(screen.queryByTestId('connection-test-pill')).toBeNull()
  })

  it('transitions idle → testing → ok on successful test', async () => {
    const onTest = vi.fn<() => Promise<ConnectionTestResult>>(() =>
      Promise.resolve({ ok: true, detail: 'Authenticated as abc' }),
    )
    render(<ConnectionTest label="Test" onTest={onTest} />)

    fireEvent.click(screen.getByTestId('connection-test-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('connection-test').getAttribute('data-state')).toBe('ok')
    })
    expect(screen.getByTestId('connection-test-pill').textContent).toContain(
      'Authenticated as abc',
    )
    expect(onTest).toHaveBeenCalledTimes(1)
  })

  it('transitions idle → testing → fail when onTest returns {ok:false}', async () => {
    const onTest = vi.fn<() => Promise<ConnectionTestResult>>(() =>
      Promise.resolve({ ok: false, detail: '403 — invalid key' }),
    )
    render(<ConnectionTest label="Test" onTest={onTest} />)

    fireEvent.click(screen.getByTestId('connection-test-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('connection-test').getAttribute('data-state')).toBe('fail')
    })
    expect(screen.getByTestId('connection-test-pill').textContent).toContain('403')
  })

  it('coerces a thrown exception to fail state with the error message', async () => {
    const onTest = vi.fn<() => Promise<ConnectionTestResult>>(() =>
      Promise.reject(new Error('Network unreachable')),
    )
    render(<ConnectionTest label="Test" onTest={onTest} />)

    fireEvent.click(screen.getByTestId('connection-test-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('connection-test').getAttribute('data-state')).toBe('fail')
    })
    expect(screen.getByTestId('connection-test-pill').textContent).toContain(
      'Network unreachable',
    )
  })

  it('fires onResult after the test resolves, with the resolved value', async () => {
    const onResult = vi.fn()
    const result: ConnectionTestResult = { ok: true, detail: 'All good' }
    render(
      <ConnectionTest label="Test" onTest={() => Promise.resolve(result)} onResult={onResult} />,
    )

    fireEvent.click(screen.getByTestId('connection-test-btn'))

    await waitFor(() => expect(onResult).toHaveBeenCalled())
    expect(onResult).toHaveBeenCalledWith(result)
  })

  it('disables the button while testing is in flight (no double-fire)', async () => {
    let resolveTest: (v: ConnectionTestResult) => void = () => {}
    const onTest = vi.fn<() => Promise<ConnectionTestResult>>(
      () => new Promise((r) => { resolveTest = r }),
    )
    render(<ConnectionTest label="Test" onTest={onTest} />)

    fireEvent.click(screen.getByTestId('connection-test-btn'))
    await waitFor(() => {
      expect(screen.getByTestId('connection-test').getAttribute('data-state')).toBe('testing')
    })

    // Button should be disabled mid-test; further clicks must not re-fire.
    expect(
      (screen.getByTestId('connection-test-btn') as HTMLButtonElement).disabled,
    ).toBe(true)
    fireEvent.click(screen.getByTestId('connection-test-btn'))
    expect(onTest).toHaveBeenCalledTimes(1)

    // Settle the promise so React Testing Library can unmount cleanly.
    resolveTest({ ok: true })
    await waitFor(() => {
      expect(screen.getByTestId('connection-test').getAttribute('data-state')).toBe('ok')
    })
  })

  it('respects the disabled prop — no test fires', () => {
    const onTest = vi.fn()
    render(<ConnectionTest label="Test" onTest={onTest} disabled />)
    const btn = screen.getByTestId('connection-test-btn') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    fireEvent.click(btn)
    expect(onTest).not.toHaveBeenCalled()
  })
})
