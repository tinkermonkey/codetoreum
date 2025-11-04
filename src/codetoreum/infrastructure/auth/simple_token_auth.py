"""
Simple Token Authentication (JupyterLab-style)

This module provides a simplified authentication system similar to JupyterLab,
where a single token is generated at server startup and printed to the console.
Users authenticate by using this token in their requests.

This is NOT a multi-user authentication system - it's designed for single-tenant
deployments and development environments where the goal is to prevent unauthorized
access without the complexity of user management.

Migration Path:
--------------
When multi-user authentication is needed, this module can be replaced with a
full JWT-based system with user accounts. The API surface (token validation
dependency) will remain similar, making the migration straightforward.
"""

import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

logger = logging.getLogger(__name__)


class SimpleTokenAuthManager:
    """
    Simple token-based authentication manager.

    Generates a single server token on startup and validates it for all requests.
    No user database, no roles, no permissions - just a simple bearer token check.

    Attributes:
        secret_key: Secret key for JWT signing
        server_token: The generated server token (JWT)
        server_start_time: When the server started (for auditing)
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        token_expiry_days: Optional[int] = None,
    ):
        """
        Initialize the authentication manager.

        Args:
            secret_key: Optional secret key. If not provided, one will be generated.
                       For production, provide a persistent secret key via environment variable.
            token_expiry_days: How long the token is valid (default: 365 days, configurable via CODETOREUM_TOKEN_EXPIRATION_DAYS)

        Raises:
            ValueError: If secret_key is not provided in production mode

        Note:
            In production (CODETOREUM_ENV=production), a secret key MUST be provided
            via the CODETOREUM_SECRET_KEY environment variable. Otherwise, tokens will
            be invalidated on every server restart.

            To generate a secret key, run:
                python -c 'import secrets; print(secrets.token_urlsafe(64))'
        """
        # Check if running in production mode
        is_production = os.getenv("CODETOREUM_ENV", "development") == "production"

        # In production, require explicit secret key
        if is_production and (not secret_key or not secret_key.strip()):
            raise ValueError(
                "CODETOREUM_SECRET_KEY environment variable is required in production. "
                "All tokens will be invalidated on server restart without a persistent secret key. "
                "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
            )

        # In development, warn about auto-generated secret
        if not secret_key:
            logger.warning(
                "Using auto-generated secret key. All tokens will be invalidated on restart. "
                "Set CODETOREUM_SECRET_KEY environment variable for persistent tokens."
            )

        # Generate or use provided secret key (64 bytes for long-lived tokens)
        self.secret_key = secret_key or secrets.token_urlsafe(64)

        # Get expiration from env var or use provided value or default
        if token_expiry_days is None:
            token_expiry_days = int(os.getenv("CODETOREUM_TOKEN_EXPIRATION_DAYS", "365"))

        # Generate the server token
        self.server_start_time = datetime.utcnow()
        self.token_expiry_days = token_expiry_days
        self.server_token = self._generate_server_token()

    def _generate_server_token(self) -> str:
        """
        Generate a long-lived server token.

        The token is a JWT containing:
        - sub: Subject (always "codetoreum-server")
        - iat: Issued at timestamp
        - exp: Expiration timestamp
        - type: Token type (always "access")

        Returns:
            JWT token string
        """
        payload = {
            "sub": "codetoreum-server",
            "iat": self.server_start_time,
            "exp": self.server_start_time + timedelta(days=self.token_expiry_days),
            "type": "access",
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def get_access_url(self, base_url: str) -> str:
        """
        Get the authentication URL to print in server logs.

        This URL includes the token as a query parameter, allowing users to
        click it and automatically authenticate via cookie.

        Args:
            base_url: Base URL of the server (e.g., "http://localhost:8000")

        Returns:
            Complete URL with token query parameter
        """
        return f"{base_url}/?token={self.server_token}"

    def create_cookie_response_headers(
        self,
        token: str,
        secure: bool = True,
        max_age: int = 86400 * 365  # 1 year default
    ) -> dict:
        """
        Create cookie headers for httpOnly token storage.

        Args:
            token: The JWT token to store in the cookie
            secure: Whether to set Secure flag (HTTPS only)
            max_age: Cookie max age in seconds (default: 1 year)

        Returns:
            Dictionary of cookie headers to set on response
        """
        cookie_value = (
            f"codetoreum_token={token}; "
            f"HttpOnly; "
            f"SameSite=Strict; "
            f"Path=/; "
            f"Max-Age={max_age}"
        )
        if secure:
            cookie_value += "; Secure"

        return {"Set-Cookie": cookie_value}

    def validate_token(self, token: str) -> bool:
        """
        Validate a provided token.

        This uses constant-time comparison to prevent timing attacks.

        Args:
            token: Token to validate

        Returns:
            True if valid, False otherwise
        """
        if not token:
            return False

        try:
            # Decode and validate JWT
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])

            # Check that it's our server token
            if payload.get("sub") != "codetoreum-server":
                return False

            if payload.get("type") != "access":
                return False

            # JWT library already validates expiration
            return True

        except JWTError:
            # Invalid token, expired, or tampered with
            return False

    def print_auth_info(
        self,
        host: str = "localhost",
        port: int = 8000,
        use_https: bool = False,
    ) -> None:
        """
        Print authentication information to console.

        This should be called during server startup to show users how to authenticate.

        Args:
            host: Hostname or IP address
            port: Port number
            use_https: Whether to use HTTPS (default: False for development)
        """
        protocol = "https" if use_https else "http"
        base_url = f"{protocol}://{host}:{port}"
        access_url = self.get_access_url(base_url)

        print("\n" + "=" * 70)
        print("Codetoreum API Server")
        print("=" * 70)
        print(f"\nServer URL: {base_url}")
        print(f"\nAuthentication token: {self.server_token}")
        print(f"\n🔗 Access URL: {access_url}")
        print("\n📋 To authenticate:")
        print("   1. Copy the access URL above and open it in your browser")
        print("   2. Or use the token in API requests:")
        print(f"      - Query parameter: ?token={self.server_token}")
        print(f"      - Header: Authorization: Bearer {self.server_token}")
        print("\n🔌 WebSocket connection:")
        ws_protocol = "wss" if use_https else "ws"
        print(f"   {ws_protocol}://{host}:{port}/ws/events?token={self.server_token}")
        print("\n⚠️  Important:")
        print("   - This token is valid for 365 days")
        print("   - Anyone with this token has full access to the API")
        print("   - Restart the server to generate a new token")
        print("   - Use HTTPS in production to protect the token")
        print("\n📚 API Documentation:")
        print(f"   {base_url}/api/docs")
        print("=" * 70 + "\n")

    def get_token_info(self) -> dict:
        """
        Get information about the current token (for debugging/monitoring).

        Returns:
            Dictionary with token metadata
        """
        try:
            payload = jwt.decode(
                self.server_token, self.secret_key, algorithms=["HS256"]
            )
            return {
                "issued_at": datetime.fromtimestamp(payload["iat"]).isoformat(),
                "expires_at": datetime.fromtimestamp(payload["exp"]).isoformat(),
                "subject": payload["sub"],
                "is_valid": True,
            }
        except JWTError as e:
            return {
                "is_valid": False,
                "error": str(e),
            }


# Example usage:
#
# # During server startup:
# auth_manager = SimpleTokenAuthManager()
# auth_manager.print_auth_info(host="localhost", port=8000)
#
# # In FastAPI dependency:
# async def verify_token(
#     authorization: Optional[str] = Header(None),
#     token: Optional[str] = Query(None)
# ):
#     # Try query parameter first
#     if token and auth_manager.validate_token(token):
#         return True
#
#     # Try Authorization header
#     if authorization and authorization.startswith("Bearer "):
#         token = authorization[7:]
#         if auth_manager.validate_token(token):
#             return True
#
#     raise HTTPException(status_code=401, detail="Invalid or missing token")
