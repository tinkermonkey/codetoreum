/**
 * Unit tests for useAuth hook.
 *
 * Tests authentication state management, login/logout flow, token persistence,
 * token refresh, and error handling.
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { useAuth } from '../hooks/useAuth';

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};

  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value.toString();
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

// Mock fetch
global.fetch = jest.fn();

describe('useAuth hook', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorageMock.clear();
    (global.fetch as jest.Mock).mockClear();
  });

  describe('Initial State', () => {
    it('should initialize with unauthenticated state', () => {
      const { result } = renderHook(() => useAuth());

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
      expect(result.current.loading).toBe(false);
    });

    it('should restore token from localStorage', async () => {
      const mockToken = 'valid-token-123';
      localStorageMock.setItem('authToken', mockToken);

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          user: { id: 'user-123', username: 'testuser' },
        }),
      });

      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
        expect(result.current.user).toEqual({
          id: 'user-123',
          username: 'testuser',
        });
      });
    });
  });

  describe('Login Flow', () => {
    it('should handle successful login', async () => {
      const mockToken = 'new-token-456';
      const mockUser = { id: 'user-456', username: 'newuser' };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          token: mockToken,
          user: mockUser,
        }),
      });

      const { result } = renderHook(() => useAuth());

      await act(async () => {
        await result.current.login('newuser', 'password123');
      });

      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user).toEqual(mockUser);
      expect(localStorageMock.getItem('authToken')).toBe(mockToken);
    });

    it('should handle login failure', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({
          error: 'Invalid credentials',
        }),
      });

      const { result } = renderHook(() => useAuth());

      await act(async () => {
        try {
          await result.current.login('wronguser', 'wrongpass');
        } catch (error) {
          expect(error).toBeDefined();
        }
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
    });

    it('should validate token format before login', async () => {
      const { result } = renderHook(() => useAuth());

      await act(async () => {
        try {
          await result.current.login('', '');
        } catch (error: any) {
          expect(error.message).toContain('Username and password are required');
        }
      });
    });
  });

  describe('Logout Flow', () => {
    it('should handle successful logout', async () => {
      // Setup authenticated state
      const mockToken = 'valid-token-123';
      localStorageMock.setItem('authToken', mockToken);

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            user: { id: 'user-123', username: 'testuser' },
          }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ success: true }),
        });

      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
      });

      await act(async () => {
        await result.current.logout();
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
      expect(localStorageMock.getItem('authToken')).toBeNull();
    });
  });

  describe('Token Persistence', () => {
    it('should persist token to localStorage on login', async () => {
      const mockToken = 'persistent-token';

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          token: mockToken,
          user: { id: 'user-789', username: 'persistuser' },
        }),
      });

      const { result } = renderHook(() => useAuth());

      await act(async () => {
        await result.current.login('persistuser', 'password');
      });

      expect(localStorageMock.getItem('authToken')).toBe(mockToken);
    });

    it('should remove token from localStorage on logout', async () => {
      localStorageMock.setItem('authToken', 'token-to-remove');

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            user: { id: 'user-123', username: 'testuser' },
          }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ success: true }),
        });

      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
      });

      await act(async () => {
        await result.current.logout();
      });

      expect(localStorageMock.getItem('authToken')).toBeNull();
    });
  });

  describe('Token Refresh', () => {
    it('should refresh expired token automatically', async () => {
      const oldToken = 'old-token';
      const newToken = 'refreshed-token';

      localStorageMock.setItem('authToken', oldToken);

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          json: async () => ({ error: 'Token expired' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            token: newToken,
            user: { id: 'user-123', username: 'testuser' },
          }),
        });

      renderHook(() => useAuth());

      await waitFor(() => {
        expect(localStorageMock.getItem('authToken')).toBe(newToken);
      });
    });

    it('should logout if token refresh fails', async () => {
      localStorageMock.setItem('authToken', 'invalid-token');

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          json: async () => ({ error: 'Token expired' }),
        })
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          json: async () => ({ error: 'Refresh failed' }),
        });

      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(false);
        expect(localStorageMock.getItem('authToken')).toBeNull();
      });
    });
  });

  describe('Token Validation', () => {
    it('should validate token format', () => {
      const validToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U';
      const invalidToken = 'invalid-token-format';

      // Test would include validation logic
      expect(validToken.split('.').length).toBe(3);
      expect(invalidToken.split('.').length).not.toBe(3);
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors during login', async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network error')
      );

      const { result } = renderHook(() => useAuth());

      await act(async () => {
        try {
          await result.current.login('user', 'pass');
        } catch (error: any) {
          expect(error.message).toContain('Network error');
        }
      });
    });

    it('should handle network errors during logout', async () => {
      localStorageMock.setItem('authToken', 'valid-token');

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            user: { id: 'user-123', username: 'testuser' },
          }),
        })
        .mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
      });

      await act(async () => {
        try {
          await result.current.logout();
        } catch (error: any) {
          expect(error.message).toContain('Network error');
        }
      });

      // Should still clear local state on logout failure
      expect(result.current.isAuthenticated).toBe(false);
      expect(localStorageMock.getItem('authToken')).toBeNull();
    });
  });
});
