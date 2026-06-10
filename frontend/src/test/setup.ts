import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
// The /vitest entry ships vitest-flavoured matcher types (the default entry
// references jest's global types, which are not installed here).
import '@testing-library/jest-dom/vitest'
import '@/i18n'

// Cleanup after each test
afterEach(() => {
  cleanup()
})
