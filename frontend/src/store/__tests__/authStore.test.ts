/**
 * Authentication Store Tests
 *
 * Tests for the Zustand-based authentication store.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useAuthStore, cleanupAuthStore } from '../authStore'

describe('authStore', () => {
  beforeEach(() => {
    // Clear sessionStorage before each test
    sessionStorage.clear()

    // Reset store to initial state
    useAuthStore.setState({
      isAuthenticated: false,
      isLoading: false,
      error: null,
      lastAuthTime: null,
    })
  })

  afterEach(() => {
    // Cleanup event listeners
    cleanupAuthStore()
  })

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useAuthStore.getState()

      expect(state.isAuthenticated).toBe(false)
      expect(state.isLoading).toBe(false)
      expect(state.error).toBe(null)
      expect(state.lastAuthTime).toBe(null)
    })
  })

  describe('setAuthenticated', () => {
    it('should set authenticated to true with timestamp', () => {
      const beforeTime = Date.now()

      useAuthStore.getState().setAuthenticated(true)

      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(true)
      expect(state.error).toBe(null)
      expect(state.lastAuthTime).toBeGreaterThanOrEqual(beforeTime)
      expect(state.lastAuthTime).toBeLessThanOrEqual(Date.now())
    })

    it('should set authenticated to false and clear timestamp', () => {
      // First set to true
      useAuthStore.getState().setAuthenticated(true)
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
      expect(useAuthStore.getState().lastAuthTime).not.toBe(null)

      // Then set to false
      useAuthStore.getState().setAuthenticated(false)

      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(false)
      expect(state.lastAuthTime).toBe(null)
    })

    it('should clear error when setting authenticated', () => {
      // Set an error first
      useAuthStore.getState().setError('Test error')
      expect(useAuthStore.getState().error).toBe('Test error')

      // Set authenticated
      useAuthStore.getState().setAuthenticated(true)

      const state = useAuthStore.getState()
      expect(state.error).toBe(null)
    })
  })

  describe('setLoading', () => {
    it('should set loading state', () => {
      useAuthStore.getState().setLoading(true)
      expect(useAuthStore.getState().isLoading).toBe(true)

      useAuthStore.getState().setLoading(false)
      expect(useAuthStore.getState().isLoading).toBe(false)
    })
  })

  describe('setError', () => {
    it('should set error and clear loading', () => {
      useAuthStore.getState().setLoading(true)
      useAuthStore.getState().setError('Test error')

      const state = useAuthStore.getState()
      expect(state.error).toBe('Test error')
      expect(state.isLoading).toBe(false)
    })

    it('should clear error when set to null', () => {
      useAuthStore.getState().setError('Test error')
      expect(useAuthStore.getState().error).toBe('Test error')

      useAuthStore.getState().setError(null)
      expect(useAuthStore.getState().error).toBe(null)
    })
  })

  describe('clearAuth', () => {
    it('should reset all state to initial values', () => {
      // Set some state
      useAuthStore.getState().setAuthenticated(true)
      useAuthStore.getState().setLoading(true)
      useAuthStore.getState().setError('Test error')

      // Clear auth
      useAuthStore.getState().clearAuth()

      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(false)
      expect(state.isLoading).toBe(false)
      expect(state.error).toBe(null)
      expect(state.lastAuthTime).toBe(null)
    })
  })

  describe('persistence', () => {
    it('should persist authentication state to sessionStorage', () => {
      useAuthStore.getState().setAuthenticated(true)

      // Check sessionStorage
      const stored = sessionStorage.getItem('auth-storage')
      expect(stored).not.toBe(null)

      if (stored) {
        const parsed = JSON.parse(stored)
        expect(parsed.state.isAuthenticated).toBe(true)
        expect(parsed.state.lastAuthTime).not.toBe(null)
      }
    })

    it('should not persist loading and error states', () => {
      useAuthStore.getState().setLoading(true)
      useAuthStore.getState().setError('Test error')

      const stored = sessionStorage.getItem('auth-storage')

      if (stored) {
        const parsed = JSON.parse(stored)
        // Loading and error should not be in persisted state
        expect(parsed.state.isLoading).toBeUndefined()
        expect(parsed.state.error).toBeUndefined()
      }
    })

    it('should restore authentication state from sessionStorage', () => {
      // Simulate persisted state
      const mockState = {
        state: {
          isAuthenticated: true,
          lastAuthTime: Date.now(),
        },
        version: 0,
      }
      sessionStorage.setItem('auth-storage', JSON.stringify(mockState))

      // Create new store instance (simulates page reload)
      // In Zustand v5, the store automatically rehydrates on creation
      const state = useAuthStore.getState()

      expect(state.isAuthenticated).toBe(true)
      expect(state.lastAuthTime).toBe(mockState.state.lastAuthTime)
    })
  })

  describe('auth:unauthorized event', () => {
    it('should clear auth on unauthorized event', () => {
      // Set authenticated
      useAuthStore.getState().setAuthenticated(true)
      expect(useAuthStore.getState().isAuthenticated).toBe(true)

      // Dispatch unauthorized event
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))

      // Should clear auth
      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(false)
      expect(state.error).toBe(null)
      expect(state.lastAuthTime).toBe(null)
    })
  })
})
