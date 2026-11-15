import type { ReactNode } from 'react'

// A list that may grow with the user's data scrolls inside this box instead
// of stretching the page. Static class names so Tailwind keeps them.
const MAX_HEIGHT = {
  sm: 'max-h-80',
  md: 'max-h-[28rem]',
} as const

interface ScrollListProps {
  children: ReactNode
  size?: keyof typeof MAX_HEIGHT
  className?: string
  testId?: string
}

export function ScrollList({ children, size = 'md', className = '', testId }: ScrollListProps) {
  return (
    <div className={`${MAX_HEIGHT[size]} overflow-y-auto ${className}`.trim()} data-testid={testId}>
      {children}
    </div>
  )
}
