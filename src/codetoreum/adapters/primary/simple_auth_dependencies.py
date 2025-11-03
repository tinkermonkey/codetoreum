"""
FastAPI Simple Authentication Dependencies

Provides FastAPI dependencies for the simplified JupyterLab-style token authentication.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Header, Query, status

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

    async def require_auth(
        self,
        authorization: Optional[str] = Header(None),
        token: Optional[str] = Query(None),
    ) -> bool:
        """
        Require authentication for the endpoint.

        Checks for token in two places (in order):
        1. Query parameter: ?token=...
        2. Authorization header: Bearer ...

        This dependency can be used on any endpoint that requires authentication.

        Args:
            authorization: Authorization header (Bearer token)
            token: Token from query parameter

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
        # Try query parameter first (for initial web UI authentication)
        if token:
            if self.auth_manager.validate_token(token):
                return True
            # Invalid token provided
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Try Authorization header
        if authorization:
            if not authorization.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authorization header format. Expected: Bearer <token>",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            token = authorization[7:]  # Remove "Bearer " prefix
            if self.auth_manager.validate_token(token):
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
            detail="Authentication required. Provide token via ?token=... or Authorization: Bearer header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async def optional_auth(
        self,
        authorization: Optional[str] = Header(None),
        token: Optional[str] = Query(None),
    ) -> bool:
        """
        Optional authentication for the endpoint.

        Same as require_auth, but returns False instead of raising an exception
        if no valid token is provided.

        Args:
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
            return await self.require_auth(authorization, token)
        except HTTPException:
            return False


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
