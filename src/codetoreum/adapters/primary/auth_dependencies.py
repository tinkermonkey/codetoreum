"""FastAPI authentication and authorization dependencies.

This module provides FastAPI dependencies for authentication and
authorization using JWT tokens, API keys, and session cookies.
"""

from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from codetoreum.domain.user import AuthContext, Permission
from codetoreum.ports.input.authentication import (
    AuthenticationError,
    IAuthenticationPort,
)

# HTTP Bearer scheme for JWT tokens
bearer_scheme = HTTPBearer(auto_error=False)


class AuthDependencies:
    """Authentication and authorization dependencies for FastAPI.

    Provides dependency injection functions for FastAPI endpoints
    to authenticate and authorize requests.

    Attributes:
        auth_service: Authentication service
    """

    def __init__(self, auth_service: IAuthenticationPort):
        """Initialize auth dependencies.

        Args:
            auth_service: Authentication service
        """
        self.auth_service = auth_service

    async def get_current_user(
        self,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
        x_api_key: Optional[str] = Header(None),
    ) -> AuthContext:
        """Get current authenticated user from JWT token or API key.

        This dependency can be used on any endpoint that requires authentication.

        Args:
            credentials: HTTP Bearer credentials (JWT token)
            x_api_key: API key from X-API-Key header

        Returns:
            Authentication context

        Raises:
            HTTPException: 401 if authentication fails
        """
        # Try API key first
        if x_api_key:
            try:
                return await self.auth_service.validate_api_key(x_api_key)
            except AuthenticationError as e:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=str(e),
                    headers={"WWW-Authenticate": "Bearer"},
                ) from e

        # Try JWT token
        if credentials:
            token = credentials.credentials
            try:
                return await self.auth_service.validate_token(token)
            except AuthenticationError as e:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=str(e),
                    headers={"WWW-Authenticate": "Bearer"},
                ) from e

        # No authentication provided
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async def get_optional_user(
        self,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
        x_api_key: Optional[str] = Header(None),
    ) -> Optional[AuthContext]:
        """Get current authenticated user or None if not authenticated.

        This dependency can be used on endpoints that optionally support authentication.

        Args:
            credentials: HTTP Bearer credentials (JWT token)
            x_api_key: API key from X-API-Key header

        Returns:
            Authentication context or None
        """
        try:
            return await self.get_current_user(credentials, x_api_key)
        except HTTPException:
            return None

    def require_permission(self, permission: Permission):
        """Create a dependency that requires a specific permission.

        Example usage:
        ```python
        @app.get("/workflows")
        async def list_workflows(
            auth: AuthContext = Depends(auth_deps.require_permission(Permission.WORKFLOW_VIEW))
        ):
            ...
        ```

        Args:
            permission: Required permission

        Returns:
            Dependency function
        """

        async def permission_checker(
            auth_context: AuthContext = Depends(self.get_current_user),
        ) -> AuthContext:
            """Check if user has required permission."""
            if not auth_context.has_permission(permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission.value} required",
                )
            return auth_context

        return permission_checker

    def require_any_permission(self, *permissions: Permission):
        """Create a dependency that requires any of the specified permissions.

        Args:
            *permissions: Required permissions (any of them)

        Returns:
            Dependency function
        """

        async def permission_checker(
            auth_context: AuthContext = Depends(self.get_current_user),
        ) -> AuthContext:
            """Check if user has any of the required permissions."""
            if not any(auth_context.has_permission(perm) for perm in permissions):
                perm_list = ", ".join(p.value for p in permissions)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: one of [{perm_list}] required",
                )
            return auth_context

        return permission_checker

    def require_all_permissions(self, *permissions: Permission):
        """Create a dependency that requires all of the specified permissions.

        Args:
            *permissions: Required permissions (all of them)

        Returns:
            Dependency function
        """

        async def permission_checker(
            auth_context: AuthContext = Depends(self.get_current_user),
        ) -> AuthContext:
            """Check if user has all of the required permissions."""
            if not all(auth_context.has_permission(perm) for perm in permissions):
                perm_list = ", ".join(p.value for p in permissions)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: all of [{perm_list}] required",
                )
            return auth_context

        return permission_checker


# Example usage in FastAPI endpoints:
#
# from fastapi import FastAPI, Depends
# from codetoreum.adapters.primary.auth_dependencies import AuthDependencies
# from codetoreum.domain.user import AuthContext, Permission
#
# app = FastAPI()
# auth_deps = AuthDependencies(auth_service)
#
# @app.get("/workflows")
# async def list_workflows(
#     auth: AuthContext = Depends(auth_deps.require_permission(Permission.WORKFLOW_VIEW))
# ):
#     """List workflows (requires WORKFLOW_VIEW permission)."""
#     return {"workflows": []}
#
# @app.post("/workflows")
# async def create_workflow(
#     auth: AuthContext = Depends(auth_deps.require_permission(Permission.WORKFLOW_CREATE))
# ):
#     """Create workflow (requires WORKFLOW_CREATE permission)."""
#     return {"workflow_id": "123"}
#
# @app.get("/public")
# async def public_endpoint(
#     auth: Optional[AuthContext] = Depends(auth_deps.get_optional_user)
# ):
#     """Public endpoint (optional authentication)."""
#     if auth:
#         return {"message": f"Hello, {auth.username}!"}
#     return {"message": "Hello, guest!"}
