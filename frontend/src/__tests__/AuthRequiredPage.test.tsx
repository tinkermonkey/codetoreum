/**
 * Tests for AuthRequiredPage.
 *
 * This is a static informational page shown when the dashboard has no valid
 * session — it takes no props and performs no auth logic itself (that lives
 * in useAuth / the router). It just needs to render the sign-in instructions.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import AuthRequiredPage from '../pages/AuthRequiredPage'

describe('AuthRequiredPage', () => {
  it('renders sign-in instructions', () => {
    render(<AuthRequiredPage />)

    expect(screen.getByText('Sign in with your server token')).toBeInTheDocument()
    expect(screen.getAllByText(/Access URL/).length).toBeGreaterThan(0)
  })
})
