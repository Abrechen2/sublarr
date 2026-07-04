import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { BackendSelect } from '../BackendSelect'

const backends = [
  { name: 'ollama', display_name: 'Ollama (Local LLM)', configured: false },
  { name: 'deepl', display_name: 'DeepL', configured: true },
  { name: 'claude', display_name: 'Anthropic Claude', configured: false },
] as any

describe('BackendSelect', () => {
  it('marks unconfigured backends except ollama when unconfiguredLabel given', () => {
    render(
      <BackendSelect
        value="deepl"
        onChange={() => {}}
        backends={backends}
        unconfiguredLabel="nicht konfiguriert"
      />
    )
    expect(screen.getByRole('option', { name: 'DeepL' })).toBeInTheDocument()
    expect(
      screen.getByRole('option', { name: /Anthropic Claude \(nicht konfiguriert\)/ })
    ).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Ollama (Local LLM)' })).toBeInTheDocument()
  })

  it('adds an inherit option and emits its value', () => {
    const onChange = vi.fn()
    render(
      <BackendSelect
        value=""
        onChange={onChange}
        backends={backends}
        inheritLabel="Standardvorgabe verwenden"
        data-testid="sel"
      />
    )
    expect(
      screen.getByRole('option', { name: 'Standardvorgabe verwenden' })
    ).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('sel'), { target: { value: 'deepl' } })
    expect(onChange).toHaveBeenCalledWith('deepl')
  })
})
