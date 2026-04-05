import { useState, useId } from 'react'
import type { ReactNode } from 'react'

interface TooltipProps {
  content: string
  children: ReactNode
  /** Default: 'top' */
  position?: 'top' | 'bottom'
  maxWidth?: number
}

/**
 * Lightweight hover tooltip that wraps any inline element.
 * Mirrors the visual style of InfoTooltip (same CSS variables, arrow).
 */
export function Tooltip({ content, children, position = 'top', maxWidth = 240 }: TooltipProps) {
  const [visible, setVisible] = useState(false)
  const tooltipId = useId()

  const isTop = position === 'top'

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      {children}

      {visible && (
        <span
          id={tooltipId}
          role="tooltip"
          className="absolute z-50 rounded-md px-3 py-2 text-xs leading-relaxed shadow-lg pointer-events-none whitespace-normal"
          style={{
            width: 'max-content',
            maxWidth,
            left: '50%',
            transform: 'translateX(-50%)',
            bottom: isTop ? 'calc(100% + 7px)' : undefined,
            top: !isTop ? 'calc(100% + 7px)' : undefined,
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
          }}
        >
          {/* Arrow — border layer */}
          <span
            className="absolute left-1/2 -translate-x-1/2 w-0 h-0"
            style={isTop ? {
              top: '100%',
              borderLeft: '5px solid transparent',
              borderRight: '5px solid transparent',
              borderTop: '5px solid var(--border)',
            } : {
              bottom: '100%',
              borderLeft: '5px solid transparent',
              borderRight: '5px solid transparent',
              borderBottom: '5px solid var(--border)',
            }}
          />
          {/* Arrow — fill layer */}
          <span
            className="absolute left-1/2 -translate-x-1/2 w-0 h-0"
            style={isTop ? {
              top: '100%',
              marginTop: '-1px',
              borderLeft: '4px solid transparent',
              borderRight: '4px solid transparent',
              borderTop: '4px solid var(--bg-elevated)',
            } : {
              bottom: '100%',
              marginBottom: '-1px',
              borderLeft: '4px solid transparent',
              borderRight: '4px solid transparent',
              borderBottom: '4px solid var(--bg-elevated)',
            }}
          />
          {content}
        </span>
      )}
    </span>
  )
}
