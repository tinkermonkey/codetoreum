## API Authentication Guide

### Overview

The Codetoreum API uses a simplified single-token authentication system similar to JupyterLab. This approach provides security without the complexity of multi-user management, making it ideal for single-tenant deployments and development environments.

**This is NOT a multi-user system.** All authenticated requests share the same access level. For production deployments requiring user-specific access control, see the [Migration to Multi-User Auth](#migration-to-multi-user-auth) section.

---

### How It Works

1. **Server Startup**: When the API server starts, it generates a random JWT token
2. **Console Output**: The token and authentication URL are printed to the console
3. **User Authentication**: Copy the URL to your browser or use the token in API requests
4. **Token Validation**: All protected endpoints validate the token before allowing access

---

### Getting Started

#### Step 1: Start the Server

```bash
python -m uvicorn codetoreum.adapters.primary.fastapi_app:app --host 0.0.0.0 --port 8000
```

#### Step 2: Copy the Authentication URL

The console will display output like this:

```
======================================================================
Codetoreum API Server
======================================================================

Server URL: http://localhost:8000

Authentication token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

🔗 Access URL: http://localhost:8000/?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

📋 To authenticate:
   1. Copy the access URL above and open it in your browser
   2. Or use the token in API requests:
      - Query parameter: ?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
      - Header: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

🔌 WebSocket connection:
   ws://localhost:8000/ws/events?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

⚠️  Important:
   - This token is valid for 365 days
   - Anyone with this token has full access to the API
   - Restart the server to generate a new token
   - Use HTTPS in production to protect the token

📚 API Documentation:
   http://localhost:8000/api/docs
======================================================================
```

#### Step 3: Use the Token

**Option A: Browser (for Web UI)**

Click the access URL. Your browser will navigate to the Codetoreum web interface with the token automatically set.

**Option B: API Requests (Authorization Header)**

```bash
curl -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  http://localhost:8000/api/v1/workflows
```

**Option C: API Requests (Query Parameter)**

```bash
curl "http://localhost:8000/api/v1/workflows?token=YOUR_TOKEN_HERE"
```

**Option D: WebSocket Connection**

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/events?token=YOUR_TOKEN_HERE');
```

---

### Token Details

#### Token Structure

The authentication token is a JSON Web Token (JWT) with the following payload:

```json
{
  "sub": "codetoreum-server",
  "type": "access",
  "iat": 1730635200,
  "exp": 1762171200
}
```

- **sub**: Subject (always "codetoreum-server")
- **type**: Token type (always "access")
- **iat**: Issued at timestamp (Unix epoch)
- **exp**: Expiration timestamp (Unix epoch, 365 days from issuance)

#### Token Validation

The server validates tokens by:

1. Verifying the JWT signature using the server's secret key
2. Checking that the subject is "codetoreum-server"
3. Checking that the type is "access"
4. Verifying the token hasn't expired
5. Using constant-time comparison to prevent timing attacks

---

### Configuration

#### Environment Variables

**CODETOREUM_AUTH_SECRET**

Provide a custom secret key for JWT signing. If not set, a random key is generated on each startup.

```bash
export CODETOREUM_AUTH_SECRET="your-secure-secret-key-here"
python -m uvicorn codetoreum.adapters.primary.fastapi_app:app
```

**Important**: Use a persistent secret key in production to prevent token invalidation on restarts.

**CODETOREUM_DISABLE_AUTH**

Disable authentication entirely (for development/testing only).

```bash
export CODETOREUM_DISABLE_AUTH=true
python -m uvicorn codetoreum.adapters.primary.fastapi_app:app
```

**API_HOST** / **API_PORT** / **API_USE_HTTPS**

Configure the server URL displayed in the console output.

```bash
export API_HOST=example.com
export API_PORT=443
export API_USE_HTTPS=true
python -m uvicorn codetoreum.adapters.primary.fastapi_app:app
```

---

### API Endpoints

#### Public Endpoints (No Authentication Required)

These endpoints are accessible without a token:

- `GET /api/v2/health` - Health check
- `GET /api/v2/health/ready` - Readiness check
- `GET /api/docs` - OpenAPI documentation
- `GET /api/redoc` - ReDoc documentation

#### Protected Endpoints (Authentication Required)

All other API endpoints require authentication. Examples:

- `POST /api/v1/workflows` - Start a workflow
- `GET /api/v1/executions` - List executions
- `GET /api/v1/executions/{id}` - Get execution status
- `PATCH /api/v1/configurations/projects/{name}` - Update project config

For a complete list, see the [API Documentation](http://localhost:8000/api/docs).

#### Authentication Debug Endpoint

- `GET /api/v2/auth/token-info` - Get token metadata (requires authentication)

Returns information about the current token:

```json
{
  "issued_at": "2025-11-03T10:00:00",
  "expires_at": "2026-11-03T10:00:00",
  "subject": "codetoreum-server",
  "is_valid": true
}
```

---

### Security Considerations

#### Threat Model

This authentication system is designed for:

- **Single-tenant deployments** (one team/organization)
- **Trusted environments** (internal network, VPN, or controlled cloud environment)
- **Development and testing** (local development, CI/CD pipelines)

#### Security Limitations

1. **Single Token**: Everyone shares the same token
   - No user-specific audit trail
   - Cannot revoke individual user access
   - All authenticated users have full permissions

2. **Token Visibility**: Initial URL contains token
   - Visible in browser history
   - May appear in server logs
   - Use HTTPS to prevent network interception

3. **No Rotation**: Token valid until server restart
   - Restart server to generate new token
   - Previously issued tokens become invalid

#### Security Best Practices

1. **Use HTTPS in Production**
   ```bash
   # Deploy behind a reverse proxy with TLS
   nginx -> Codetoreum API (HTTP localhost)
   ```

2. **Network Isolation**
   ```bash
   # Bind to localhost only
   uvicorn app:app --host 127.0.0.1

   # Or use firewall rules to restrict access
   ```

3. **Persistent Secret Key**
   ```bash
   # Generate a secure secret key
   python -c "import secrets; print(secrets.token_urlsafe(32))"

   # Store in environment
   export CODETOREUM_AUTH_SECRET="generated-secret-key"
   ```

4. **Regular Token Rotation**
   ```bash
   # Restart server to generate new token
   # Schedule periodic restarts or implement manual rotation
   ```

5. **Monitor Access Logs**
   ```bash
   # Check for suspicious API access patterns
   # All requests include X-Correlation-ID header for tracking
   ```

---

### Migration to Multi-User Auth

When your deployment grows to require multi-user access control, migrate to a full JWT-based authentication system:

#### Step 1: Implement User Management

- Add user database (PostgreSQL, etc.)
- Implement user registration and login endpoints
- Add password hashing (bcrypt, argon2)

#### Step 2: Add Role-Based Access Control (RBAC)

- Define roles: Admin, ProjectManager, Developer, Viewer
- Map permissions to roles
- Add permission checks on endpoints

#### Step 3: Update Authentication Flow

- Replace `SimpleTokenAuthManager` with `JWTAuthenticationService`
- Add login endpoint that issues short-lived access tokens
- Implement refresh token flow
- Add token revocation mechanism

#### Step 4: Update API Dependencies

The `SimpleAuthDependencies.require_auth` dependency can be replaced with minimal code changes:

```python
# Old (simple auth)
@app.get("/workflows")
async def list_workflows(
    authenticated: bool = Depends(auth_deps.require_auth)
):
    ...

# New (multi-user auth)
@app.get("/workflows")
async def list_workflows(
    auth_context: AuthContext = Depends(auth_deps.get_current_user)
):
    # auth_context.user_id, auth_context.roles, auth_context.permissions
    ...
```

For detailed migration instructions, see `documentation/01_design/02_high_level_arch.md` (Gen 2 Architecture).

---

### Troubleshooting

#### "401 Unauthorized" on all requests

- **Cause**: Token not provided or invalid
- **Solution**: Check that you're including the token in Authorization header or query parameter

#### Token in URL not working

- **Cause**: Token was copied incorrectly or has expired
- **Solution**: Copy the full token from server console output. If expired, restart server.

#### "Invalid authorization header format"

- **Cause**: Missing "Bearer " prefix in Authorization header
- **Solution**: Use `Authorization: Bearer YOUR_TOKEN`, not `Authorization: YOUR_TOKEN`

#### Token works in browser but not API

- **Cause**: Browser may have stored token in localStorage, API requires explicit header
- **Solution**: Add Authorization header to API requests

#### Different token after server restart

- **Cause**: By design - new token generated on each startup (unless using CODETOREUM_AUTH_SECRET)
- **Solution**: Set persistent secret key via CODETOREUM_AUTH_SECRET environment variable

---

### Examples

#### Python (requests library)

```python
import requests

# Store token (from server console)
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Make authenticated request
response = requests.post(
    "http://localhost:8000/api/v1/workflows",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "project_name": "my-project",
        "work_item_id": "123",
        "pipeline_name": "default"
    }
)

print(response.json())
```

#### JavaScript (fetch API)

```javascript
const TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...";

// Make authenticated request
fetch("http://localhost:8000/api/v1/workflows", {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${TOKEN}`,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    project_name: "my-project",
    work_item_id: "123",
    pipeline_name: "default"
  })
})
.then(response => response.json())
.then(data => console.log(data));
```

#### curl

```bash
# Store token in variable
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Make authenticated request
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_name":"my-project","work_item_id":"123","pipeline_name":"default"}' \
  http://localhost:8000/api/v1/workflows
```

---

### Summary

- ✅ **Simple**: No user accounts, roles, or permissions to manage
- ✅ **Secure**: JWT-based token validation with expiration
- ✅ **Flexible**: Works with HTTP headers, query parameters, and WebSockets
- ⚠️ **Single-tenant**: Not suitable for multi-user SaaS deployments
- 🔄 **Upgradeable**: Clear migration path to full authentication system

For questions or issues, consult the [API Documentation](http://localhost:8000/api/docs) or refer to the codebase at `src/codetoreum/infrastructure/auth/`.
