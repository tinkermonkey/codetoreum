# Security Improvement: httpOnly Cookie-Based Authentication

## Overview

This document describes the security improvements made to Codetoreum's authentication system to prevent XSS (Cross-Site Scripting) token theft attacks.

## Problem: localStorage Vulnerability

### Original Implementation
```typescript
// VULNERABLE - Token accessible to JavaScript
localStorage.setItem('token', token)
const token = localStorage.getItem('token')
```

### Attack Scenario
1. Attacker injects malicious script via XSS vulnerability
2. Script reads `localStorage.getItem('token')`
3. Token is exfiltrated to attacker's server
4. Attacker gains full API access with stolen token

### Impact
- Complete account takeover
- Full access to all API endpoints
- Ability to create/modify/delete data
- No user awareness of compromise

## Solution: httpOnly Cookies

### New Implementation

#### Backend (Python/FastAPI)
```python
# Set httpOnly cookie - inaccessible to JavaScript
response.set_cookie(
    key="codetoreum_token",
    value=token,
    httponly=True,      # Prevents JavaScript access (XSS protection)
    secure=True,        # HTTPS only in production
    samesite="strict",  # CSRF protection
    max_age=86400 * 365 # 1 year
)
```

#### Frontend (TypeScript/React)
```typescript
// Create API client with cookie support
const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,  // Send cookies automatically
})

// No manual token handling needed - browser manages cookies
```

### Security Benefits

1. **XSS Protection**
   - httpOnly cookies cannot be read by JavaScript
   - Even if attacker injects malicious script, token is inaccessible
   - Tokens are only sent by the browser in HTTP requests

2. **CSRF Protection**
   - SameSite=Strict prevents cross-origin cookie sending
   - Tokens only sent to same-origin requests
   - Mitigates cross-site request forgery attacks

3. **Secure Transport**
   - Secure flag ensures HTTPS-only transmission in production
   - Prevents man-in-the-middle token interception

4. **No Client-Side Token Storage**
   - No localStorage/sessionStorage usage
   - Reduces attack surface for token theft
   - Browser manages secure storage automatically

## Implementation Details

### Authentication Flow

1. **Initial Authentication**
   ```
   User clicks URL with token →
   Frontend makes API call with ?token=... →
   Backend validates token & sets httpOnly cookie →
   Frontend removes token from URL →
   Future requests use cookie automatically
   ```

2. **Subsequent Requests**
   ```
   Browser automatically includes cookie in requests →
   Backend validates cookie token →
   Response sent with fresh cookie (if needed)
   ```

3. **Logout**
   ```
   User clicks logout →
   Frontend calls /api/v2/auth/logout →
   Backend clears httpOnly cookie →
   Browser stops sending cookie
   ```

### Backend Changes

#### Authentication Manager (`simple_token_auth.py`)
- Added `create_cookie_response_headers()` method
- Generates secure cookie configuration
- Supports environment-based Secure flag

#### Authentication Dependencies (`simple_auth_dependencies.py`)
- Updated to check cookies first, then query params, then headers
- Automatically sets cookie when token provided in URL
- Clears invalid cookies
- Added logout support

#### FastAPI App (`fastapi_app.py`)
- Updated CORS to allow credentials (`withCredentials: true`)
- Added logout endpoint: `POST /api/v2/auth/logout`
- Cookie set automatically on first authenticated request

### Frontend Changes

#### API Client (`api/client.ts`)
- Added `withCredentials: true` for cookie support
- Removed manual Authorization header injection
- Added `authApi.logout()` function
- Updated error handling (no localStorage clearing)

#### useAuth Hook (`hooks/useAuth.ts`)
- Removed all localStorage usage
- Check auth via API call (cookie sent automatically)
- Token state removed (not accessible in client code)
- Logout calls API endpoint to clear cookie

#### useWebSocket Hook (`hooks/useWebSocket.ts`)
- Removed token from WebSocket URL
- Uses cookies for WebSocket authentication
- Browser sends cookies automatically with WS upgrade request
- Updated to use `isAuthenticated` instead of `token`

### Testing Updates

#### E2E Tests (`e2e/auth.spec.ts`)
- Updated to use `context.addCookies()` instead of localStorage
- Tests verify httpOnly cookie properties
- Tests verify cookie headers in requests
- Tests validate cookie-based authentication flow

## Migration Path

### For Existing Users

Existing users with tokens in localStorage will need to re-authenticate:

1. User visits application
2. Old localStorage token ignored
3. User sees "Authentication Required" page
4. User clicks new authentication URL with token
5. httpOnly cookie set automatically
6. User authenticated via secure cookies

### Breaking Changes

- **Frontend**: `useAuth()` no longer exposes `token` property
  - Use `isAuthenticated` boolean instead
- **WebSocket**: `useWebSocket(token)` changed to `useWebSocket(isAuthenticated)`
- **Tests**: Must use cookies instead of localStorage

## Additional Security Considerations

### Implemented
- ✅ httpOnly cookies (XSS protection)
- ✅ SameSite=Strict (CSRF protection)
- ✅ Secure flag in production (HTTPS only)
- ✅ Logout endpoint to clear cookies
- ✅ Automatic cookie refresh on requests

### Recommended (Future Enhancements)
- [ ] **Token Rotation**: Short-lived access tokens with refresh tokens
- [ ] **Token Revocation**: Server-side token invalidation
- [ ] **Session Timeout**: Automatic logout after inactivity
- [ ] **CSRF Tokens**: Additional CSRF protection layer
- [ ] **Rate Limiting**: Prevent brute force attacks
- [ ] **IP Whitelisting**: Restrict access by IP address

## Configuration

### Environment Variables

```bash
# Enable HTTPS-only cookies in production
API_USE_HTTPS=true

# Set persistent secret key (required in production)
CODETOREUM_SECRET_KEY="your-secret-key-here"

# Token expiration (default: 365 days)
CODETOREUM_TOKEN_EXPIRATION_DAYS=365

# CORS origins (production should be specific)
CODETOREUM_ALLOWED_ORIGINS="https://app.example.com,https://dashboard.example.com"
```

### Production Checklist

- [ ] Set `API_USE_HTTPS=true`
- [ ] Configure `CODETOREUM_SECRET_KEY` (persistent)
- [ ] Set specific `CODETOREUM_ALLOWED_ORIGINS`
- [ ] Enable HTTPS/TLS on server
- [ ] Review token expiration settings
- [ ] Test authentication flow end-to-end

## Comparison

| Feature | Old (localStorage) | New (httpOnly Cookies) |
|---------|-------------------|------------------------|
| XSS Protection | ❌ None | ✅ Full |
| CSRF Protection | ⚠️ Manual | ✅ Built-in (SameSite) |
| Secure Transport | ⚠️ Manual | ✅ Enforced (Secure flag) |
| Client Access | ✅ Full access | ❌ No access (better) |
| Browser Support | ✅ All browsers | ✅ All modern browsers |
| Mobile Apps | ✅ Easy | ⚠️ Requires cookie support |
| API Clients | ✅ Easy | ⚠️ Need cookie jar |

## References

- [OWASP: HttpOnly Cookie Attribute](https://owasp.org/www-community/HttpOnly)
- [MDN: Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)
- [OWASP: SameSite Cookie Attribute](https://owasp.org/www-community/SameSite)
- [OWASP: Cross-Site Scripting (XSS)](https://owasp.org/www-community/attacks/xss/)
- [OWASP: Cross-Site Request Forgery (CSRF)](https://owasp.org/www-community/attacks/csrf)

## Support

For questions or issues related to authentication security:
- Review this document
- Check backend logs for authentication errors
- Verify CORS configuration for your environment
- Ensure cookies are enabled in browser
- Test with browser DevTools (Network tab → Cookies)
