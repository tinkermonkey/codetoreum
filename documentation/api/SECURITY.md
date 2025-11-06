# API Security Best Practices

This document outlines security best practices for using the Codetoreum API, including authentication, token management, and production deployment guidelines.

## Table of Contents

- [Authentication](#authentication)
- [Token Management](#token-management)
- [Secure Storage](#secure-storage)
- [Environment Configuration](#environment-configuration)
- [Network Security](#network-security)
- [Production Deployment](#production-deployment)
- [Security Checklist](#security-checklist)

## Authentication

### Bearer Token Authentication

The Codetoreum API uses Bearer token authentication. Always include the `Authorization` header with your requests:

```bash
curl -H "Authorization: Bearer YOUR_API_TOKEN" \
  https://api.codetoreum.com/api/v2/work-items/
```

### Token Formats

- **API Tokens**: Long-lived tokens for programmatic access (format: `ct_live_...` or `ct_test_...`)
- **Session Tokens**: Short-lived tokens for web applications (format: `ct_session_...`)
- **Service Tokens**: Scoped tokens for CI/CD and automation (format: `ct_service_...`)

### Never Commit Tokens

**DON'T** commit tokens to version control:

```python
# ❌ BAD: Token hardcoded in source
client = CodetoreumClient(api_token="ct_live_abc123...")
```

**DO** use environment variables:

```python
# ✅ GOOD: Token from environment
import os
client = CodetoreumClient(api_token=os.getenv("CODETOREUM_API_TOKEN"))
```

## Token Management

### Token Lifecycle

1. **Creation**: Generate tokens through the web UI or API
2. **Usage**: Use tokens for API requests
3. **Rotation**: Rotate tokens every 90 days (recommended)
4. **Revocation**: Immediately revoke compromised tokens

### Token Rotation Strategy

```python
# Example: Graceful token rotation
import os
from datetime import datetime, timedelta

class TokenRotator:
    def __init__(self):
        self.primary_token = os.getenv("CODETOREUM_API_TOKEN")
        self.fallback_token = os.getenv("CODETOREUM_API_TOKEN_FALLBACK")
        self.rotation_date = datetime.fromisoformat(
            os.getenv("TOKEN_ROTATION_DATE", datetime.now().isoformat())
        )

    def get_active_token(self):
        """Get the currently active token with automatic fallback."""
        # Use fallback if rotation date has passed
        if datetime.now() > self.rotation_date:
            return self.fallback_token or self.primary_token
        return self.primary_token
```

### Token Scope Limitation

Always use the minimum required scope for your tokens:

```python
# Service token with limited scope (read-only)
service_client = CodetoreumClient(
    api_token=os.getenv("CODETOREUM_SERVICE_TOKEN"),  # read:work_items only
)

# Admin token with full scope (use sparingly)
admin_client = CodetoreumClient(
    api_token=os.getenv("CODETOREUM_ADMIN_TOKEN"),  # full access
)
```

## Secure Storage

### Environment Variables

Use environment variables for token storage:

```bash
# .env file (DO NOT commit to git)
CODETOREUM_API_TOKEN=ct_live_abc123...
CODETOREUM_API_URL=https://api.codetoreum.com
```

```python
# Load from .env file
from dotenv import load_dotenv
import os

load_dotenv()

client = CodetoreumClient(
    api_token=os.getenv("CODETOREUM_API_TOKEN"),
    base_url=os.getenv("CODETOREUM_API_URL", "http://localhost:8000")
)
```

### Secret Management Services

For production environments, use dedicated secret management:

#### AWS Secrets Manager

```python
import boto3
from botocore.exceptions import ClientError

def get_codetoreum_token():
    """Retrieve API token from AWS Secrets Manager."""
    secret_name = "prod/codetoreum/api_token"
    region_name = "us-east-1"

    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=region_name)

    try:
        response = client.get_secret_value(SecretId=secret_name)
        return response['SecretString']
    except ClientError as e:
        raise Exception(f"Error retrieving secret: {e}")

# Usage
from codetoreum_client import CodetoreumClient

client = CodetoreumClient(api_token=get_codetoreum_token())
```

#### HashiCorp Vault

```python
import hvac

def get_codetoreum_token():
    """Retrieve API token from HashiCorp Vault."""
    vault_client = hvac.Client(url='https://vault.example.com:8200')
    vault_client.auth.approle.login(
        role_id=os.getenv('VAULT_ROLE_ID'),
        secret_id=os.getenv('VAULT_SECRET_ID')
    )

    secret = vault_client.secrets.kv.v2.read_secret_version(
        path='codetoreum/api_token'
    )
    return secret['data']['data']['token']
```

#### Azure Key Vault

```python
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

def get_codetoreum_token():
    """Retrieve API token from Azure Key Vault."""
    key_vault_name = "my-keyvault"
    key_vault_uri = f"https://{key_vault_name}.vault.azure.net"

    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=key_vault_uri, credential=credential)

    secret = client.get_secret("codetoreum-api-token")
    return secret.value
```

### File-Based Secrets (Development Only)

For local development, you can use encrypted files:

```python
from cryptography.fernet import Fernet
import os

class SecureTokenStore:
    def __init__(self, key_file=".token.key", token_file=".token.enc"):
        self.key_file = key_file
        self.token_file = token_file
        self._ensure_key_exists()

    def _ensure_key_exists(self):
        """Generate encryption key if it doesn't exist."""
        if not os.path.exists(self.key_file):
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            os.chmod(self.key_file, 0o600)  # Read/write for owner only

    def save_token(self, token: str):
        """Encrypt and save token."""
        with open(self.key_file, 'rb') as f:
            key = f.read()

        fernet = Fernet(key)
        encrypted_token = fernet.encrypt(token.encode())

        with open(self.token_file, 'wb') as f:
            f.write(encrypted_token)
        os.chmod(self.token_file, 0o600)

    def load_token(self) -> str:
        """Decrypt and load token."""
        with open(self.key_file, 'rb') as f:
            key = f.read()

        fernet = Fernet(key)

        with open(self.token_file, 'rb') as f:
            encrypted_token = f.read()

        return fernet.decrypt(encrypted_token).decode()

# Usage
store = SecureTokenStore()
# One-time setup
# store.save_token("ct_live_abc123...")

# Load token securely
client = CodetoreumClient(api_token=store.load_token())
```

## Environment Configuration

### Development vs Production

Use different tokens and configurations for each environment:

```python
import os

class Config:
    """Environment-specific configuration."""

    def __init__(self):
        self.env = os.getenv("APP_ENV", "development")

        if self.env == "production":
            self.api_token = self._get_production_token()
            self.api_url = "https://api.codetoreum.com"
            self.verify_ssl = True
            self.timeout = 30
        elif self.env == "staging":
            self.api_token = os.getenv("CODETOREUM_STAGING_TOKEN")
            self.api_url = "https://staging-api.codetoreum.com"
            self.verify_ssl = True
            self.timeout = 45
        else:  # development
            self.api_token = os.getenv("CODETOREUM_DEV_TOKEN")
            self.api_url = "http://localhost:8000"
            self.verify_ssl = False
            self.timeout = 60

    def _get_production_token(self):
        """Retrieve production token from secure storage."""
        # Use secret management service in production
        from .secrets import get_codetoreum_token
        return get_codetoreum_token()

# Usage
config = Config()
client = CodetoreumClient(
    api_token=config.api_token,
    base_url=config.api_url,
    verify_ssl=config.verify_ssl,
    timeout=config.timeout
)
```

### Docker Secrets

For Docker deployments:

```yaml
# docker-compose.yml
version: '3.8'
services:
  app:
    image: myapp:latest
    secrets:
      - codetoreum_api_token
    environment:
      - CODETOREUM_API_TOKEN_FILE=/run/secrets/codetoreum_api_token

secrets:
  codetoreum_api_token:
    external: true
```

```python
# Load from Docker secret
import os

def get_token():
    token_file = os.getenv("CODETOREUM_API_TOKEN_FILE")
    if token_file and os.path.exists(token_file):
        with open(token_file, 'r') as f:
            return f.read().strip()
    return os.getenv("CODETOREUM_API_TOKEN")

client = CodetoreumClient(api_token=get_token())
```

## Network Security

### TLS/SSL Verification

Always verify SSL certificates in production:

```python
# ✅ GOOD: SSL verification enabled (default)
client = CodetoreumClient(
    api_token=token,
    base_url="https://api.codetoreum.com",
    verify_ssl=True  # Default
)

# ⚠️ ONLY for local development
dev_client = CodetoreumClient(
    api_token=token,
    base_url="http://localhost:8000",
    verify_ssl=False  # Only for localhost
)
```

### Request Timeouts

Always set appropriate timeouts to prevent hanging requests:

```python
# Configure timeout based on operation type
client = CodetoreumClient(
    api_token=token,
    timeout=30  # Default: 30 seconds
)

# Override for specific operations
workflow_run = client.post(
    "/api/v2/orchestrator/start",
    json={"work_item_id": "item_123"},
    timeout=120  # 2 minutes for workflow start
)
```

### Rate Limiting

Implement client-side rate limiting:

```python
import time
from functools import wraps

class RateLimiter:
    def __init__(self, max_requests=100, time_window=60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            # Remove old requests outside time window
            self.requests = [req for req in self.requests
                           if now - req < self.time_window]

            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_window - (now - self.requests[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    self.requests = []

            self.requests.append(now)
            return func(*args, **kwargs)
        return wrapper

# Usage
rate_limiter = RateLimiter(max_requests=100, time_window=60)

@rate_limiter
def create_work_item(title, description):
    return client.work_items.create(title=title, description=description)
```

## Production Deployment

### Kubernetes Secrets

```yaml
# k8s-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: codetoreum-api-secret
type: Opaque
stringData:
  api_token: ct_live_abc123...
```

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  template:
    spec:
      containers:
      - name: app
        image: myapp:latest
        env:
        - name: CODETOREUM_API_TOKEN
          valueFrom:
            secretKeyRef:
              name: codetoreum-api-secret
              key: api_token
```

### Logging and Monitoring

Never log API tokens:

```python
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ❌ BAD: Token exposed in logs
logger.info(f"Using token: {api_token}")

# ✅ GOOD: Token masked
logger.info(f"Using token: {api_token[:10]}...")

# ✅ BETTER: No token in logs
logger.info("Initializing Codetoreum client")
```

### Error Handling

Don't expose sensitive information in error messages:

```python
try:
    client = CodetoreumClient(api_token=token)
    result = client.work_items.list()
except AuthenticationError as e:
    # ❌ BAD: Exposes token
    logger.error(f"Auth failed with token {token}: {e}")

    # ✅ GOOD: Generic error message
    logger.error("Authentication failed. Please check your API token.")
    raise
```

## Security Checklist

### Development

- [ ] API tokens stored in environment variables or .env files
- [ ] .env files added to .gitignore
- [ ] No tokens committed to version control
- [ ] SSL verification disabled only for localhost
- [ ] Appropriate request timeouts configured

### Staging

- [ ] Separate staging API tokens used
- [ ] Tokens stored in secure secret management system
- [ ] SSL/TLS verification enabled
- [ ] Rate limiting implemented
- [ ] Logging configured without exposing secrets

### Production

- [ ] Production API tokens stored in secret management service (AWS Secrets Manager, Vault, etc.)
- [ ] Token rotation strategy implemented (90-day cycle)
- [ ] Principle of least privilege applied to token scopes
- [ ] SSL/TLS verification enabled and enforced
- [ ] Network security configured (firewalls, VPNs)
- [ ] Rate limiting and retry logic implemented
- [ ] Comprehensive error handling without exposing secrets
- [ ] Logging and monitoring configured
- [ ] Security scanning integrated into CI/CD pipeline
- [ ] Incident response plan documented
- [ ] Regular security audits scheduled

### Monitoring

- [ ] Failed authentication attempts monitored
- [ ] Unusual API usage patterns detected
- [ ] Token expiration alerts configured
- [ ] API rate limit alerts configured
- [ ] Security events logged to SIEM

## Incident Response

### If a Token is Compromised

1. **Immediately Revoke** the compromised token via web UI or API
2. **Generate** a new token with appropriate scope
3. **Update** all services using the old token
4. **Audit** API logs for unauthorized access
5. **Document** the incident and update security procedures

### Revoke Token via API

```python
# Revoke compromised token immediately
admin_client = CodetoreumClient(api_token=admin_token)
admin_client.post("/api/v2/auth/tokens/revoke", json={
    "token_id": "token_abc123"
})
```

## Additional Resources

- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [NIST Guidelines for Application Security](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
- [CIS Controls](https://www.cisecurity.org/controls/)

---

**Last Updated**: 2025-11-05
**Version**: 2.0

For questions or security concerns, please contact security@codetoreum.com
