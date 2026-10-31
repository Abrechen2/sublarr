import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

import { InstanceEditor } from '../InstanceEditor'

// The server restores a masked key only for the same address (#61 security
// review), so a changed URL must show an empty key, not a mask it will drop.
describe('InstanceEditor', () => {
  it('asks for the key again when the URL changes', () => {
    const onChange = vi.fn()
    const value = JSON.stringify([
      { id: 'a1', name: 'Sonarr', url: 'http://192.168.10.5:8989', api_key: '***configured***', path_mapping: '' },
    ])
    render(<InstanceEditor value={value} onChange={onChange} label="Sonarr" />)

    fireEvent.change(screen.getByDisplayValue('http://192.168.10.5:8989'), {
      target: { value: 'http://192.168.10.6:8989' },
    })

    const saved = JSON.parse(onChange.mock.calls.at(-1)[0])
    expect(saved[0].url).toBe('http://192.168.10.6:8989')
    expect(saved[0].api_key).toBe('')
    expect(saved[0].id).toBe('a1')
  })
})
