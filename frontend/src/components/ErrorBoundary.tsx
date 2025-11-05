import React from 'react'
import { Button } from './ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card'

/**
 * Error Boundary Props
 */
interface ErrorBoundaryProps {
  children: React.ReactNode
  fallback?: React.ComponentType<ErrorBoundaryFallbackProps>
}

/**
 * Error Boundary State
 */
interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  errorInfo: React.ErrorInfo | null
}

/**
 * Error Boundary Fallback Props
 */
export interface ErrorBoundaryFallbackProps {
  error: Error | null
  errorInfo: React.ErrorInfo | null
  resetError: () => void
}

/**
 * Default Error Fallback Component
 */
const DefaultErrorFallback: React.FC<ErrorBoundaryFallbackProps> = ({
  error,
  errorInfo,
  resetError,
}) => {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <Card className="max-w-2xl w-full">
        <CardHeader>
          <CardTitle className="text-red-600">Something went wrong</CardTitle>
          <CardDescription>
            An unexpected error occurred. You can try reloading the page or contact support if the
            problem persists.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Error Message */}
          <div>
            <h3 className="font-semibold text-sm text-gray-700 mb-2">Error Message:</h3>
            <pre className="bg-red-50 text-red-800 p-3 rounded text-sm overflow-auto">
              {error?.message || 'Unknown error'}
            </pre>
          </div>

          {/* Stack Trace (only in development) */}
          {import.meta.env.DEV && errorInfo && (
            <div>
              <h3 className="font-semibold text-sm text-gray-700 mb-2">Stack Trace:</h3>
              <pre className="bg-gray-100 text-gray-800 p-3 rounded text-xs overflow-auto max-h-64">
                {errorInfo.componentStack}
              </pre>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-3 pt-4">
            <Button onClick={resetError} variant="default">
              Try Again
            </Button>
            <Button onClick={() => window.location.reload()} variant="outline">
              Reload Page
            </Button>
            {import.meta.env.DEV && (
              <Button
                onClick={() => {
                  console.error('Error:', error)
                  console.error('Error Info:', errorInfo)
                }}
                variant="outline"
              >
                Log to Console
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * React Error Boundary Component
 *
 * Catches JavaScript errors anywhere in the component tree and displays a fallback UI
 * instead of crashing the entire application.
 *
 * Features:
 * - Catches errors in render methods, lifecycle methods, and hooks
 * - Displays user-friendly error message with recovery options
 * - Shows stack trace in development mode
 * - Provides reset functionality to attempt recovery
 * - Logs errors for debugging
 *
 * Usage:
 * ```tsx
 * <ErrorBoundary>
 *   <App />
 * </ErrorBoundary>
 * ```
 *
 * With custom fallback:
 * ```tsx
 * <ErrorBoundary fallback={CustomErrorComponent}>
 *   <App />
 * </ErrorBoundary>
 * ```
 *
 * Limitations:
 * - Does NOT catch errors in event handlers (use try-catch)
 * - Does NOT catch errors in async code (use try-catch or promises)
 * - Does NOT catch errors during SSR
 * - Does NOT catch errors in the error boundary itself
 *
 * For event handlers and async code, use traditional error handling:
 * ```tsx
 * const handleClick = async () => {
 *   try {
 *     await riskyOperation()
 *   } catch (error) {
 *     // Handle error
 *   }
 * }
 * ```
 */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    }
  }

  /**
   * Update state when an error is caught
   */
  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return {
      hasError: true,
      error,
    }
  }

  /**
   * Log error details for debugging
   */
  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('[ErrorBoundary] Caught error:', error)
    console.error('[ErrorBoundary] Error info:', errorInfo)

    this.setState({
      errorInfo,
    })

    // TODO: Send error to monitoring service (e.g., Sentry, LogRocket)
    // Example:
    // if (import.meta.env.PROD) {
    //   Sentry.captureException(error, { contexts: { react: { componentStack: errorInfo.componentStack } } })
    // }
  }

  /**
   * Reset error state to attempt recovery
   */
  resetError = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    })
  }

  render(): React.ReactNode {
    if (this.state.hasError) {
      const FallbackComponent = this.props.fallback || DefaultErrorFallback

      return (
        <FallbackComponent
          error={this.state.error}
          errorInfo={this.state.errorInfo}
          resetError={this.resetError}
        />
      )
    }

    return this.props.children
  }
}

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
