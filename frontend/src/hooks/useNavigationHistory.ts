import { useEffect, useCallback, useRef } from "react"
import { useNavigate, useRouterState } from "@tanstack/react-router"

const STORAGE_KEY = "nav_history"
const MAX_STACK_SIZE = 50

/**
 * Tab-scoped navigation history that powers intuitive Back button behavior.
 *
 * Uses sessionStorage (unique per browser tab) to maintain a stack of visited URLs.
 * When `goBack` is called, the most recent entry is popped and navigated to.
 * Falls back to a provided default route when the stack is empty.
 *
 * Two parts:
 * - `useNavigationTracker()` — call once in the root layout to record every route change
 * - `useNavigationHistory()` — call in any page that needs a Back button
 */

function getStack(): string[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function setStack(stack: string[]) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(stack))
}

// Module-level flag shared across hook instances in the same tab.
// Set to true before a goBack navigation so the tracker skips pushing.
let skipNextPush = false

/**
 * Records every route change into sessionStorage. Must be called once
 * in a component that is always mounted (e.g. the root layout).
 */
export function useNavigationTracker() {
  const routerState = useRouterState()
  const currentPath = routerState.location.pathname
  const prevPathRef = useRef<string | null>(null)

  useEffect(() => {
    if (skipNextPush) {
      skipNextPush = false
      prevPathRef.current = currentPath
      return
    }

    if (prevPathRef.current && prevPathRef.current !== currentPath) {
      const stack = getStack()
      stack.push(prevPathRef.current)
      if (stack.length > MAX_STACK_SIZE) {
        stack.splice(0, stack.length - MAX_STACK_SIZE)
      }
      setStack(stack)
    }

    prevPathRef.current = currentPath
  }, [currentPath])
}

/**
 * Returns a `goBack` function that pops the most recent page from the
 * navigation stack. If the stack is empty, navigates to `fallback`.
 */
export function useNavigationHistory() {
  const navigate = useNavigate()

  const goBack = useCallback(
    (fallback: string) => {
      const stack = getStack()
      const target = stack.pop()
      setStack(stack)

      skipNextPush = true
      navigate({ to: target || fallback })
    },
    [navigate],
  )

  return { goBack }
}
