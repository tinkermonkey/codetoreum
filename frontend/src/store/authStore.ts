import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

/**
 * Authentication State Interface
 *
 * Note: This store tracks authentication state and stores the token for WebSocket use.
 * HTTP API requests use httpOnly cookies for security (XSS protection).
 * The token is stored in sessionStorage for WebSocket connections which cannot use cookies.
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

  /** Authentication token (stored for WebSocket connections only) */
  token: string | null

  // Actions
  setAuthenticated: (authenticated: boolean, token?: string) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  clearAuth: () => void
  getToken: () => string | null
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
/**
 * Zustand store with persistence
 * - Only persists isAuthenticated and lastAuthTime
 * - Does not persist transient states (isLoading, error)
 * - Uses sessionStorage (cleared when browser/tab closes)
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      isAuthenticated: false,
      isLoading: true, // Start as loading to prevent race conditions
      error: null,
      lastAuthTime: null,
      token: null,

      setAuthenticated: (authenticated: boolean, token?: string) => {
        set({
          isAuthenticated: authenticated,
          error: null,
          lastAuthTime: authenticated ? Date.now() : null,
          token: authenticated && token ? token : get().token
        })
      },

      setLoading: (loading: boolean) => {
        set({ isLoading: loading })
      },

      setError: (error: string | null) => {
        set({ error, isLoading: false })
      },

      clearAuth: () =>
        set({
          isAuthenticated: false,
          isLoading: false,
          error: null,
          lastAuthTime: null,
          token: null
        }),

      getToken: () => get().token,
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        isAuthenticated: state.isAuthenticated,
        lastAuthTime: state.lastAuthTime,
        token: state.token
      })
    }
  )
)

/**
 * Setup global event listener for 401 unauthorized responses
 * This allows the API client to notify the auth store when authentication fails
 */
let unauthorizedHandler: ((event: Event) => void) | null = null

const setupUnauthorizedListener = () => {
  if (typeof window !== 'undefined' && !unauthorizedHandler) {
    unauthorizedHandler = () => {
      useAuthStore.getState().clearAuth()
    }
    window.addEventListener('auth:unauthorized', unauthorizedHandler)
  }
}

if (typeof window !== 'undefined') {
  setupUnauthorizedListener()

  // Cleanup on page unload
  window.addEventListener('beforeunload', () => {
    if (unauthorizedHandler) {
      window.removeEventListener('auth:unauthorized', unauthorizedHandler)
      unauthorizedHandler = null
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

/**
 * Re-initialize the unauthorized event listener (useful for testing)
 */
export const reinitAuthStore = () => {
  setupUnauthorizedListener()
}
