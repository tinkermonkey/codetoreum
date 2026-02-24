import React from 'react'
import { DefaultErrorFallback } from './DefaultErrorFallback'

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
