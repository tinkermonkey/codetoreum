"""
FastAPI Simple Authentication Dependencies

Provides FastAPI dependencies for the simplified JupyterLab-style token authentication.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Header, Query, Cookie, Response, status

from codetoreum.infrastructure.auth import SimpleTokenAuthManager


class SimpleAuthDependencies:
    """
    Simple authentication dependencies for FastAPI.

    Provides dependency injection functions for FastAPI endpoints to
    authenticate requests using a single server token.

    Attributes:
        auth_manager: Simple token authentication manager
    """

    def __init__(self, auth_manager: SimpleTokenAuthManager):
        """
        Initialize auth dependencies.

        Args:
            auth_manager: Simple token authentication manager
        """
        self.auth_manager = auth_manager

    def _validate_token_format(self, token: str) -> bool:
        """
        Pre-validate token format before JWT processing.

        This prevents unnecessary CPU usage on obviously invalid tokens.
        JWT tokens should be at least 20 characters and contain dots.

        Args:
            token: Token string to validate

        Returns:
            True if format looks valid, False otherwise
        """
        if not token or len(token) < 20 or len(token) > 2000:
            return False
        if '.' not in token:
            return False
        # JWT should have 3 parts separated by dots
        parts = token.count('.')
        if parts != 2:
            return False
        return True

    async def require_auth(
        self,
        response: Response,
        codetoreum_token: Optional[str] = Cookie(None),
        authorization: Optional[str] = Header(None),
        token: Optional[str] = Query(None),
    ) -> bool:
        """
        Require authentication for the endpoint.

        Checks for token in three places (in order):
        1. httpOnly cookie: codetoreum_token (primary, most secure)
        2. Query parameter: ?token=... (for initial authentication only)
        3. Authorization header: Bearer ... (for API clients)

        When a query parameter token is provided, it will be set as an httpOnly cookie.

        This dependency can be used on any endpoint that requires authentication.

        Args:
            response: FastAPI Response object for setting cookies
            codetoreum_token: Token from httpOnly cookie (most secure)
            authorization: Authorization header (Bearer token)
            token: Token from query parameter (for initial auth)

        Returns:
            True if authenticated

        Raises:
            HTTPException: 401 if authentication fails

        Example:
            @app.get("/protected")
            async def protected_endpoint(
                authenticated: bool = Depends(auth_deps.require_auth)
            ):
                return {"message": "You are authenticated!"}
        """
        # Try httpOnly cookie first (most secure, prevents XSS)
        if codetoreum_token:
            if not self._validate_token_format(codetoreum_token):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication token format",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if self.auth_manager.validate_token(codetoreum_token):
                return True
            # Invalid cookie token - clear it
            response.delete_cookie(key="codetoreum_token", path="/")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Try query parameter (for initial web UI authentication)
        # If valid, set httpOnly cookie for future requests
        if token:
            if not self._validate_token_format(token):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication token format",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if self.auth_manager.validate_token(token):
                # Set httpOnly cookie for future requests
                import os
                use_https = os.getenv("API_USE_HTTPS", "false").lower() == "true"
                response.set_cookie(
                    key="codetoreum_token",
                    value=token,
                    httponly=True,  # Prevents JavaScript access (XSS protection)
                    secure=use_https,  # HTTPS only in production
                    samesite="strict",  # CSRF protection
                    max_age=86400 * 365,  # 1 year
                    path="/",
                )
                return True
            # Invalid token provided
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Try Authorization header (for API clients)
        if authorization:
            if not authorization.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authorization header format. Expected: Bearer <token>",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            auth_token = authorization[7:]  # Remove "Bearer " prefix

            if not self._validate_token_format(auth_token):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication token format",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if self.auth_manager.validate_token(auth_token):
                return True

            # Invalid token provided
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # No authentication provided
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide token via cookie, ?token=... or Authorization: Bearer header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async def optional_auth(
        self,
        response: Response,
        codetoreum_token: Optional[str] = Cookie(None),
        authorization: Optional[str] = Header(None),
        token: Optional[str] = Query(None),
    ) -> bool:
        """
        Optional authentication for the endpoint.

        Same as require_auth, but returns False instead of raising an exception
        if no valid token is provided.

        Args:
            response: FastAPI Response object for setting cookies
            codetoreum_token: Token from httpOnly cookie
            authorization: Authorization header (Bearer token)
            token: Token from query parameter

        Returns:
            True if authenticated, False otherwise

        Example:
            @app.get("/optional")
            async def optional_endpoint(
                authenticated: bool = Depends(auth_deps.optional_auth)
            ):
                if authenticated:
                    return {"message": "You are authenticated!"}
                else:
                    return {"message": "You are not authenticated"}
        """
        try:
            return await self.require_auth(response, codetoreum_token, authorization, token)
        except HTTPException:
            return False

    async def logout(self, response: Response) -> None:
        """
        Logout by clearing the httpOnly cookie.

        Args:
            response: FastAPI Response object for clearing cookies

        Example:
            @app.post("/logout")
            async def logout_endpoint(
                response: Response,
                _: bool = Depends(auth_deps.require_auth)
            ):
                await auth_deps.logout(response)
                return {"message": "Logged out successfully"}
        """
        response.delete_cookie(key="codetoreum_token", path="/")


# Example usage in FastAPI app:
#
# from fastapi import FastAPI, Depends
# from codetoreum.infrastructure.auth import SimpleTokenAuthManager
# from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
#
# # Create auth manager
# auth_manager = SimpleTokenAuthManager()
# auth_manager.print_auth_info()
#
# # Create auth dependencies
# auth_deps = SimpleAuthDependencies(auth_manager)
#
# app = FastAPI()
#
# @app.get("/public")
# async def public_endpoint():
#     """Public endpoint - no authentication required"""
#     return {"message": "This is public"}
#
# @app.get("/protected")
# async def protected_endpoint(
#     authenticated: bool = Depends(auth_deps.require_auth)
# ):
#     """Protected endpoint - authentication required"""
#     return {"message": "This is protected"}
#
# @app.get("/optional")
# async def optional_endpoint(
#     authenticated: bool = Depends(auth_deps.optional_auth)
# ):
#     """Optional authentication endpoint"""
#     if authenticated:
#         return {"message": "You are authenticated"}
#     return {"message": "You are not authenticated"}
