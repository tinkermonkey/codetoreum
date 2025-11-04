/**
 * Authentication Hook
 *
 * Provides simplified httpOnly cookie-based authentication (secure, XSS-protected).
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
 */

import { useState, useEffect } from 'react'
import api, { authApi } from '../api/client'

export interface AuthState {
  isAuthenticated: boolean
  isLoading: boolean
}

export function useAuth() {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
  })

  useEffect(() => {
    const initializeAuth = async () => {
      // Check for token in URL query parameter
      const urlParams = new URLSearchParams(window.location.search)
      const urlToken = urlParams.get('token')

      if (urlToken) {
        try {
          // Make a request with the token to set the httpOnly cookie
          // The backend will set the cookie when it validates the token
          await api.get('/v2/health', {
            params: { token: urlToken }
          })

          // Remove token from URL for security
          window.history.replaceState({}, document.title, window.location.pathname)

          setAuthState({
            isAuthenticated: true,
            isLoading: false,
          })
          return
        } catch (error) {
          console.error('Failed to authenticate with URL token:', error)
          setAuthState({
            isAuthenticated: false,
            isLoading: false,
          })
          return
        }
      }

      // Check if we're already authenticated by making an API call
      // The browser will automatically send the httpOnly cookie
      try {
        await api.get('/v2/auth/token-info')
        setAuthState({
          isAuthenticated: true,
          isLoading: false,
        })
      } catch (error) {
        // Not authenticated
        setAuthState({
          isAuthenticated: false,
          isLoading: false,
        })
      }
    }

    initializeAuth()

    // Listen for unauthorized events from API interceptor
    const handleUnauthorized = () => {
      setAuthState({
        isAuthenticated: false,
        isLoading: false,
      })
    }

    window.addEventListener('auth:unauthorized', handleUnauthorized)
    return () => {
      window.removeEventListener('auth:unauthorized', handleUnauthorized)
    }
  }, [])

  const logout = async () => {
    try {
      // Call logout endpoint to clear httpOnly cookie
      await authApi.logout()
    } catch (error) {
      console.error('Logout failed:', error)
    } finally {
      // Update local state regardless of API call result
      setAuthState({
        isAuthenticated: false,
        isLoading: false,
      })
    }
  }

  return {
    ...authState,
    logout,
  }
}
