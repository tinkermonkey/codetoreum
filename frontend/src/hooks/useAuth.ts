/**
 * Authentication Hook
 *
 * Provides simplified token-based authentication (JupyterLab-style).
 *
 * Flow:
 * 1. On first load, check for token in URL query parameter
 * 2. If found, store in localStorage and remove from URL
 * 3. If not found in URL, check localStorage
 * 4. If no token found, show "Authentication Required" page
 * 5. All API requests include token in Authorization header
 * 6. On 401 response, clear token and redirect to auth required page
 */

import { useState, useEffect } from 'react'

export interface AuthState {
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
}

export function useAuth() {
  const [authState, setAuthState] = useState<AuthState>({
    token: null,
    isAuthenticated: false,
    isLoading: true,
  })

  useEffect(() => {
    // Check for token in URL query parameter
    const urlParams = new URLSearchParams(window.location.search)
    const urlToken = urlParams.get('token')

    if (urlToken) {
      // Store token and clean URL
      localStorage.setItem('codetoreum_token', urlToken)
      // Remove token from URL for security
      window.history.replaceState({}, document.title, window.location.pathname)
      setAuthState({
        token: urlToken,
        isAuthenticated: true,
        isLoading: false,
      })
      return
    }

    // Check for token in localStorage
    const storedToken = localStorage.getItem('codetoreum_token')
    if (storedToken) {
      setAuthState({
        token: storedToken,
        isAuthenticated: true,
        isLoading: false,
      })
    } else {
      setAuthState({
        token: null,
        isAuthenticated: false,
        isLoading: false,
      })
    }

    // Listen for unauthorized events from API interceptor
    const handleUnauthorized = () => {
      setAuthState({
        token: null,
        isAuthenticated: false,
        isLoading: false,
      })
    }

    window.addEventListener('auth:unauthorized', handleUnauthorized)
    return () => {
      window.removeEventListener('auth:unauthorized', handleUnauthorized)
    }
  }, [])

  const logout = () => {
    localStorage.removeItem('codetoreum_token')
    setAuthState({
      token: null,
      isAuthenticated: false,
      isLoading: false,
    })
  }

  return {
    ...authState,
    logout,
  }
}
