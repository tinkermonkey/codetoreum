import React from 'react'
import { Button } from './ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card'
import type { ErrorBoundaryFallbackProps } from './ErrorBoundary'

/**
 * Default Error Fallback Component
 */
export const DefaultErrorFallback: React.FC<ErrorBoundaryFallbackProps> = ({
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
