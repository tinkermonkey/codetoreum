/**
 * Authentication Hook
 *
 * Provides simplified httpOnly cookie-based authentication (secure, XSS-protected).
 * Now uses Zustand for centralized state management.
 *
 * Flow:
 * 1. On first load, check for token in URL query parameter
 * 2. If found, make API call to set httpOnly cookie and remove from URL
 * 3. Check authentication status via API call (cookie is sent automatically)
 * 4. If no authentication found, show "Authentication Required" page
 * 5. All API requests include httpOnly cookie automatically (browser handles this)
 * 6. On 401 response, clear auth state and redirect to auth required page
 *
 * Security improvements:
 * - No localStorage usage (prevents XSS token theft)
 * - httpOnly cookies (inaccessible to JavaScript)
 * - SameSite=Strict (CSRF protection)
 * - Secure flag in production (HTTPS only)
 *
 * State Management:
 * - Uses Zustand store for global state
 * - Persists authentication status in sessionStorage
 * - Automatically syncs across components
 */

import { useEffect } from 'react'
import api, { authApi } from '../api/client'
import { useAuthStore } from '../store/authStore'

export interface AuthState {
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
}

// Global flag to ensure auth is only initialized once across all components
let authInitialized = false
let authInitializing = false

export function useAuth() {
  const {
    isAuthenticated,
    isLoading,
    error,
    setAuthenticated,
    setLoading,
    setError,
    clearAuth,
  } = useAuthStore()

  useEffect(() => {
    // Skip if already initialized or currently initializing
    if (authInitialized || authInitializing) {
      return
    }

    authInitializing = true

    // Check authentication on mount by validating the httpOnly cookie
    const initializeAuth = async () => {
      setLoading(true)

      // Check for token in URL query parameter
      const urlParams = new URLSearchParams(window.location.search)
      const urlToken = urlParams.get('token')

      if (urlToken) {
        try {
          // SECURITY NOTE: Token in URL is acceptable here because:
          // 1. It's immediately removed from URL after use
          // 2. It's only used to exchange for httpOnly cookie
          // 3. This is the initial authentication handshake
          // 4. Alternative would require separate auth page/flow

          // Make a request with the token to set the httpOnly cookie
          // The backend will set the cookie when it validates the token
          await api.get('/health', {
            params: { token: urlToken }
          })

          // CRITICAL: Remove token from URL immediately to prevent:
          // - Browser history exposure
          // - Accidental sharing of URL with token
          // - Session hijacking via URL
          window.history.replaceState({}, document.title, window.location.pathname)

          setAuthenticated(true)
          setLoading(false)
          return
        } catch (error) {
          console.error('Failed to authenticate with URL token:', error)

          // Remove token from URL even on error
          window.history.replaceState({}, document.title, window.location.pathname)

          // Set user-facing error message
          const errorMessage = error instanceof Error
            ? error.message
            : 'Authentication failed. Please check your token and try again.'

          setError(errorMessage)
          setLoading(false)
          return
        }
      }

      // Validate the httpOnly cookie
      try {
        await api.get('/auth/token-info')
        setAuthenticated(true)
      } catch (error) {
        setAuthenticated(false)
      } finally {
        setLoading(false)
        authInitializing = false
        authInitialized = true
      }
    }

    initializeAuth()

    // Run once on mount - empty deps array
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const logout = async () => {
    try {
      await authApi.logout()
    } catch (error) {
      console.error('Logout failed:', error)
    } finally {
      clearAuth()
      // Reset global flags so user can log back in
      authInitialized = false
      authInitializing = false
    }
  }

  return {
    isAuthenticated,
    isLoading,
    error,
    logout,
  }
}
