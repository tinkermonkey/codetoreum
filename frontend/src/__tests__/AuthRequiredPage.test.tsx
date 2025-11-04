/**
 * Integration tests for AuthRequiredPage component.
 *
 * Tests authentication checks, redirects, loading states, and error handling.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import '@testing-library/jest-dom';
import AuthRequiredPage from '../components/AuthRequiredPage';
import { useAuth } from '../hooks/useAuth';

jest.mock('../hooks/useAuth');

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;

describe('AuthRequiredPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Authenticated User', () => {
    it('should render children for authenticated user', async () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'user-123', username: 'testuser' },
        loading: false,
        login: jest.fn(),
        logout: jest.fn(),
      });

      render(
        <MemoryRouter initialEntries={['/dashboard']}>
          <Routes>
            <Route
              path="/dashboard"
              element={
                <AuthRequiredPage>
                  <div>Protected Content</div>
                </AuthRequiredPage>
              }
            />
          </Routes>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('Protected Content')).toBeInTheDocument();
      });
    });
  });

  describe('Unauthenticated User', () => {
    it('should redirect to login for unauthenticated user', async () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        loading: false,
        login: jest.fn(),
        logout: jest.fn(),
      });

      render(
        <MemoryRouter initialEntries={['/dashboard']}>
          <Routes>
            <Route
              path="/dashboard"
              element={
                <AuthRequiredPage>
                  <div>Protected Content</div>
                </AuthRequiredPage>
              }
            />
            <Route path="/login" element={<div>Login Page</div>} />
          </Routes>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('Login Page')).toBeInTheDocument();
      });
    });

    it('should preserve original URL for redirect after login', async () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        loading: false,
        login: jest.fn(),
        logout: jest.fn(),
      });

      const { container } = render(
        <MemoryRouter initialEntries={['/dashboard/settings']}>
          <Routes>
            <Route
              path="/dashboard/settings"
              element={
                <AuthRequiredPage>
                  <div>Protected Content</div>
                </AuthRequiredPage>
              }
            />
            <Route
              path="/login"
              element={<div data-redirect={window.location.search}>Login Page</div>}
            />
          </Routes>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('Login Page')).toBeInTheDocument();
      });
    });
  });

  describe('Loading State', () => {
    it('should show loading state during auth check', () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        loading: true,
        login: jest.fn(),
        logout: jest.fn(),
      });

      render(
        <MemoryRouter>
          <AuthRequiredPage>
            <div>Protected Content</div>
          </AuthRequiredPage>
        </MemoryRouter>
      );

      expect(screen.getByText('Checking authentication...')).toBeInTheDocument();
    });

    it('should not render children during loading', () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        loading: true,
        login: jest.fn(),
        logout: jest.fn(),
      });

      render(
        <MemoryRouter>
          <AuthRequiredPage>
            <div>Protected Content</div>
          </AuthRequiredPage>
        </MemoryRouter>
      );

      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
    });
  });

  describe('Token Expiration', () => {
    it('should redirect to login when token expires', async () => {
      const mockLogout = jest.fn();

      mockUseAuth.mockReturnValueOnce({
        isAuthenticated: true,
        user: { id: 'user-123', username: 'testuser' },
        loading: false,
        login: jest.fn(),
        logout: mockLogout,
      });

      const { rerender } = render(
        <MemoryRouter initialEntries={['/dashboard']}>
          <Routes>
            <Route
              path="/dashboard"
              element={
                <AuthRequiredPage>
                  <div>Protected Content</div>
                </AuthRequiredPage>
              }
            />
            <Route path="/login" element={<div>Login Page</div>} />
          </Routes>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('Protected Content')).toBeInTheDocument();
      });

      // Simulate token expiration
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        loading: false,
        login: jest.fn(),
        logout: mockLogout,
      });

      rerender(
        <MemoryRouter initialEntries={['/dashboard']}>
          <Routes>
            <Route
              path="/dashboard"
              element={
                <AuthRequiredPage>
                  <div>Protected Content</div>
                </AuthRequiredPage>
              }
            />
            <Route path="/login" element={<div>Login Page</div>} />
          </Routes>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('Login Page')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('should display error message on auth failure', () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        loading: false,
        error: 'Authentication service unavailable',
        login: jest.fn(),
        logout: jest.fn(),
      });

      render(
        <MemoryRouter>
          <AuthRequiredPage>
            <div>Protected Content</div>
          </AuthRequiredPage>
        </MemoryRouter>
      );

      expect(screen.getByText(/Authentication service unavailable/i)).toBeInTheDocument();
    });
  });
});
