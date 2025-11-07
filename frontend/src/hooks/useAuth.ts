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
    console.log('[useAuth] Effect running:', { isAuthenticated, isLoading })

    const initializeAuth = async () => {
      console.log('[useAuth] initializeAuth starting, setting loading=true')
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
          await api.get('/v2/health', {
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

      // Check if we're already authenticated by making an API call
      // The browser will automatically send the httpOnly cookie
      try {
        console.log('[useAuth] Checking token-info...')
        await api.get('/v2/auth/token-info')
        console.log('[useAuth] Token valid, setting authenticated=true, loading=false')
        setAuthenticated(true)
        setLoading(false)
      } catch (error) {
        // Not authenticated
        console.log('[useAuth] Token invalid, setting authenticated=false, loading=false')
        setAuthenticated(false)
        setLoading(false)
      }
    }

    // ALWAYS validate authentication, even if persisted state says authenticated
    // This ensures the cookie is still valid
    console.log('[useAuth] Calling initializeAuth() to validate cookie')
    initializeAuth()
  }, [setAuthenticated, setLoading, setError])

  const logout = async () => {
    try {
      // Call logout endpoint to clear httpOnly cookie
      await authApi.logout()
    } catch (error) {
      console.error('Logout failed:', error)
    } finally {
      // Clear authentication state
      clearAuth()
    }
  }

  return {
    isAuthenticated,
    isLoading,
    error,
    logout,
  }
}
