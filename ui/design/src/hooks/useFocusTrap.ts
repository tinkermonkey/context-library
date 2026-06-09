import { useEffect, useRef } from 'react'

const FOCUSABLE_SELECTORS = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
]

export interface UseFocusTrapOptions {
  mode?: 'modal' | 'popup'
}

export function useFocusTrap(
  ref: React.RefObject<HTMLElement>,
  isActive: boolean,
  options?: UseFocusTrapOptions
) {
  const previousActiveElementRef = useRef<HTMLElement | null>(null)
  const mode = options?.mode ?? 'modal'

  useEffect(() => {
    if (!isActive || !ref.current) return

    previousActiveElementRef.current = document.activeElement as HTMLElement

    const getFocusableElements = () => {
      if (!ref.current) return [] as HTMLElement[]
      return Array.from(
        ref.current.querySelectorAll(FOCUSABLE_SELECTORS.join(','))
      ) as HTMLElement[]
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return

      const focusableElements = getFocusableElements()
      if (focusableElements.length === 0) return

      const firstElement = focusableElements[0]
      const lastElement = focusableElements[focusableElements.length - 1]

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault()
          lastElement.focus()
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault()
          firstElement.focus()
        }
      }
    }

    const initialFocusableElements = getFocusableElements()
    if (initialFocusableElements.length > 0 && mode === 'modal') {
      initialFocusableElements[0].focus()
    }

    ref.current.addEventListener('keydown', handleKeyDown)

    return () => {
      ref.current?.removeEventListener('keydown', handleKeyDown)
      const previousElement = previousActiveElementRef.current
      if (previousElement && document.body.contains(previousElement)) {
        previousElement.focus()
      }
    }
  }, [ref, isActive, mode])
}
