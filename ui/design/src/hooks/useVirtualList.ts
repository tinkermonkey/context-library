import { useEffect, useRef, useState } from 'react'

interface UseVirtualListOptions {
  itemCount: number
  itemHeight: number
  containerHeight: number
  overscan?: number
}

interface UseVirtualListReturn {
  visibleRange: [number, number]
  containerRef: React.RefObject<HTMLDivElement>
  sentinelRef: React.RefObject<HTMLDivElement>
}

export const useVirtualList = ({
  itemCount,
  itemHeight,
  containerHeight,
  overscan = 5,
}: UseVirtualListOptions): UseVirtualListReturn => {
  const containerRef = useRef<HTMLDivElement>(null)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const [visibleRange, setVisibleRange] = useState<[number, number]>([0, Math.ceil(containerHeight / itemHeight)])

  useEffect(() => {
    const container = containerRef.current
    const sentinel = sentinelRef.current
    if (!container || !sentinel) return

    const calculateVisibleRange = () => {
      const sentinelRect = sentinel.getBoundingClientRect()
      const containerRect = container.getBoundingClientRect()

      const scrollTop = containerRect.top - sentinelRect.top

      const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan)
      const endIndex = Math.min(itemCount, Math.ceil((scrollTop + containerHeight) / itemHeight) + overscan)

      setVisibleRange(prev => {
        if (prev[0] === startIndex && prev[1] === endIndex) return prev
        return [startIndex, endIndex]
      })
    }

    container.addEventListener('scroll', calculateVisibleRange, { passive: true })
    calculateVisibleRange()

    return () => {
      container.removeEventListener('scroll', calculateVisibleRange)
    }
  }, [itemCount, itemHeight, containerHeight, overscan])

  return {
    visibleRange,
    containerRef,
    sentinelRef,
  }
}
