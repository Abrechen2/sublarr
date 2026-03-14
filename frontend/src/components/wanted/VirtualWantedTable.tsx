import { useRef, useEffect } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'

/**
 * Virtual scroll hook for Wanted list using the padding-row technique.
 * Returns ref for the scroll container + virtualItems + padding values.
 *
 * Scroll resets to top whenever `count` changes (filter applied).
 * estimatedRowHeight: collapsed row ~42px; expanded rows cause minor jitter (acceptable for v0.25.3).
 *
 * colSpan for spacer rows: 9 (count of <th> elements in Wanted.tsx thead).
 */
export function useWantedVirtualizer(count: number, estimatedRowHeight = 42) {
  const parentRef = useRef<HTMLDivElement>(null)
  const rowVirtualizer = useVirtualizer({
    count,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimatedRowHeight,
    overscan: 8,
  })

  // Reset scroll to top when count changes (new filter applied)
  useEffect(() => {
    parentRef.current?.scrollTo({ top: 0 })
  }, [count])

  const virtualItems = rowVirtualizer.getVirtualItems()
  const paddingTop = virtualItems.length > 0 ? virtualItems[0].start : 0
  const paddingBottom =
    virtualItems.length > 0
      ? rowVirtualizer.getTotalSize() - virtualItems[virtualItems.length - 1].end
      : 0

  return { parentRef, virtualItems, paddingTop, paddingBottom }
}
