import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ScrollList } from '../ScrollList'

describe('ScrollList', () => {
  it('caps the height and scrolls vertically', () => {
    render(<ScrollList testId="box"><p>a</p></ScrollList>)
    const box = screen.getByTestId('box')
    expect(box.className).toContain('overflow-y-auto')
    expect(box.className).toContain('max-h-[28rem]')
    expect(box.textContent).toBe('a')
  })

  it('offers a smaller cap for secondary lists', () => {
    render(<ScrollList testId="box" size="sm"><p>a</p></ScrollList>)
    expect(screen.getByTestId('box').className).toContain('max-h-80')
  })

  it('keeps extra classes from the caller', () => {
    render(<ScrollList testId="box" className="space-y-2"><p>a</p></ScrollList>)
    expect(screen.getByTestId('box').className).toContain('space-y-2')
  })
})
