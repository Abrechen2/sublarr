import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom'
import '@/i18n'

// Cleanup after each test
afterEach(() => {
  cleanup()
})
