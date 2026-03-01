import React from 'react'

/**
 * Hook to throw errors that will be caught by ErrorBoundary
 *
 * This hook provides a safe way to trigger error boundaries from async operations
 * and event handlers where errors normally wouldn't be caught.
 *
 * How it works:
 * 1. Returns a function that accepts an Error
 * 2. When called, updates state with a function that throws the error
 * 3. React's render cycle catches the thrown error
 * 4. Error boundary's getDerivedStateFromError catches it
 * 5. Error boundary renders fallback UI
 *
 * Safety:
 * - Uses setState's updater function to throw (safe, caught by boundaries)
 * - Does NOT create infinite render loops (error boundary stops propagation)
 * - Memoized with useCallback to prevent unnecessary re-renders
 *
 * Example:
 * ```tsx
 * const handleError = useErrorHandler()
 *
 * const handleClick = async () => {
 *   try {
 *     await riskyOperation()
 *   } catch (error) {
 *     handleError(error instanceof Error ? error : new Error(String(error)))
 *   }
 * }
 * ```
 *
 * Important: Always wrap the component using this hook with an ErrorBoundary!
 */
export const useErrorHandler = (): ((error: Error) => void) => {
  const [, setError] = React.useState<Error>()

  return React.useCallback((error: Error) => {
    // Using setState's updater function to throw is a safe pattern
    // The error will be caught by the nearest ErrorBoundary
    setError(() => {
      throw error
    })
  }, [])
}
