/**
 * SettingsNav.test.tsx — the Translation section must always be reachable.
 *
 * Regression guard for issue #151: the Translation nav group used to be
 * hidden until translation was already enabled, which (combined with the
 * /settings → /settings/general redirect) left no reachable way to enable
 * translation from the UI.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SettingsNav } from '../SettingsNav'

function renderNav() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <BrowserRouter>
      <QueryClientProvider client={qc}>
        <SettingsNav />
      </QueryClientProvider>
    </BrowserRouter>,
  )
}

describe('SettingsNav', () => {
  it('always exposes the Translation page link, even when translation is disabled', () => {
    renderNav()
    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(hrefs).toContain('/settings/translation')
  })
})
