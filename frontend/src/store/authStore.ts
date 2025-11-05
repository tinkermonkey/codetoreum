import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

/**
 * Authentication State Interface
 *
 * Note: This store tracks authentication state but does NOT store the actual token.
 * The application uses httpOnly cookies for security (XSS protection).
 * The isAuthenticated flag is derived from successful API responses.
 */
interface AuthState {
  /** Whether the user is currently authenticated */
  isAuthenticated: boolean

  /** Loading state during authentication checks */
  isLoading: boolean

  /** Last authentication error, if any */
  error: string | null

  /** Timestamp of last successful authentication */
  lastAuthTime: number | null

  // Actions
  setAuthenticated: (authenticated: boolean) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  clearAuth: () => void
}

/**
 * Zustand Store for Authentication State
 *
 * This store manages authentication state using Zustand with persistence.
 *
 * Security Model:
 * - Uses httpOnly cookies (set by backend via /v2/health endpoint)
 * - No token stored in localStorage (prevents XSS attacks)
 * - Persists only authentication status, not credentials
 * - Automatically syncs across browser tabs
 *
 * Authentication Flow:
 * 1. Token provided via URL query parameter (?token=...)
 * 2. Frontend sends token to /v2/health to set httpOnly cookie
 * 3. Backend responds with 200 OK and sets secure cookie
 * 4. Store updates isAuthenticated = true
 * 5. All subsequent requests include cookie automatically
 *
 * On 401 Unauthorized:
 * - Custom window event 'auth:unauthorized' dispatched
 * - Store clears authentication state
 * - User redirected to AuthRequiredPage
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      isAuthenticated: false,
      isLoading: false,
      error: null,
      lastAuthTime: null,

      setAuthenticated: (authenticated: boolean) =>
        set({
          isAuthenticated: authenticated,
          error: null,
          lastAuthTime: authenticated ? Date.now() : null
        }),

      setLoading: (loading: boolean) =>
        set({ isLoading: loading }),

      setError: (error: string | null) =>
        set({ error, isLoading: false }),

      clearAuth: () =>
        set({
          isAuthenticated: false,
          isLoading: false,
          error: null,
          lastAuthTime: null
        }),
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => sessionStorage), // Use sessionStorage for better security
      partialize: (state) => ({
        // Only persist authentication status, not loading/error states
        isAuthenticated: state.isAuthenticated,
        lastAuthTime: state.lastAuthTime,
      }),
    }
  )
)

/**
 * Setup global event listener for 401 unauthorized responses
 * This allows the API client to notify the auth store when authentication fails
 */
let unauthorizedHandler: ((event: Event) => void) | null = null

if (typeof window !== 'undefined') {
  unauthorizedHandler = () => {
    useAuthStore.getState().clearAuth()
  }
  window.addEventListener('auth:unauthorized', unauthorizedHandler)

  // Cleanup on page unload
  window.addEventListener('beforeunload', () => {
    if (unauthorizedHandler) {
      window.removeEventListener('auth:unauthorized', unauthorizedHandler)
    }
  })
}

/**
 * Cleanup function for testing or manual cleanup
 * Call this to remove the event listener when needed
 */
export const cleanupAuthStore = () => {
  if (typeof window !== 'undefined' && unauthorizedHandler) {
    window.removeEventListener('auth:unauthorized', unauthorizedHandler)
    unauthorizedHandler = null
  }
}
