"""Authentication API adapter for FastAPI.

This module provides REST API endpoints for authentication operations
including login, token refresh, user management, and API key management.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from codetoreum.adapters.primary.auth_dependencies import AuthDependencies
from codetoreum.config import (
    MAX_API_KEY_NAME_LENGTH,
    MAX_USERNAME_LENGTH,
    MIN_API_KEY_NAME_LENGTH,
    MIN_PASSWORD_LENGTH,
    MIN_USERNAME_LENGTH,
)
from codetoreum.domain.user import AuthContext, Permission, UserRole
from codetoreum.ports.input.authentication import (
    AuthenticationError,
    CreateAPIKeyCommand,
    CreateUserCommand,
    IAuthenticationPort,
    LoginCommand,
    UpdateUserCommand,
    UserAlreadyExistsError,
    UserNotFoundError,
    ValidationError,
)

# ============================================================================
# Request/Response Models
# ============================================================================


class LoginRequest(BaseModel):
    """Login request model."""

    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class LoginResponse(BaseModel):
    """Login response model."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    refresh_token: str | None = Field(None, description="Refresh token")


class RefreshTokenRequest(BaseModel):
    """Refresh token request model."""

    refresh_token: str = Field(..., description="Refresh token")


class CreateUserRequest(BaseModel):
    """Create user request model."""

    username: str = Field(..., min_length=MIN_USERNAME_LENGTH, max_length=MAX_USERNAME_LENGTH, description="Username")
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, description="Password")
    roles: list[UserRole] = Field(default=[UserRole.VIEWER], description="User roles")


class UpdateUserRequest(BaseModel):
    """Update user request model."""

    email: EmailStr | None = Field(None, description="Email address")
    password: str | None = Field(None, min_length=MIN_PASSWORD_LENGTH, description="Password")
    roles: list[UserRole] | None = Field(None, description="User roles")
    is_active: bool | None = Field(None, description="Active status")


class UserResponse(BaseModel):
    """User response model."""

    id: UUID = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    email: str = Field(..., description="Email address")
    roles: list[UserRole] = Field(..., description="User roles")
    is_active: bool = Field(..., description="Active status")
    is_verified: bool = Field(..., description="Verified status")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_login_at: datetime | None = Field(None, description="Last login timestamp")


class CreateAPIKeyRequest(BaseModel):
    """Create API key request model."""

    name: str = Field(..., min_length=MIN_API_KEY_NAME_LENGTH, max_length=MAX_API_KEY_NAME_LENGTH, description="API key name")
    roles: list[UserRole] = Field(
        default=[UserRole.SERVICE_ACCOUNT], description="API key roles"
    )
    expires_at: datetime | None = Field(None, description="Expiration timestamp")


class APIKeyResponse(BaseModel):
    """API key response model."""

    id: UUID = Field(..., description="API key ID")
    name: str = Field(..., description="API key name")
    key: str | None = Field(None, description="API key (only returned on creation)")
    roles: list[UserRole] = Field(..., description="API key roles")
    is_active: bool = Field(..., description="Active status")
    expires_at: datetime | None = Field(None, description="Expiration timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_used_at: datetime | None = Field(None, description="Last usage timestamp")


class MeResponse(BaseModel):
    """Current user response model."""

    user_id: UUID = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    roles: list[UserRole] = Field(..., description="User roles")
    permissions: list[str] = Field(..., description="User permissions")
    auth_method: str = Field(..., description="Authentication method")


# ============================================================================
# Authentication API Adapter
# ============================================================================


class AuthAPIAdapter:
    """Authentication API adapter for FastAPI.

    Provides REST API endpoints for authentication operations.

    Attributes:
        auth_service: Authentication service
        auth_deps: Authentication dependencies
        router: FastAPI router
    """

    def __init__(self, auth_service: IAuthenticationPort) -> None:
        """Initialize auth API adapter.

        Args:
            auth_service: Authentication service
        """
        self.auth_service = auth_service
        self.auth_deps = AuthDependencies(auth_service)
        self.router = self._create_router()

    def _create_router(self) -> APIRouter:
        """Create FastAPI router with auth endpoints."""
        router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])

        # ====================================================================
        # Public Endpoints (No Authentication Required)
        # ====================================================================

        @router.post(
            "/login",
            response_model=LoginResponse,
            status_code=status.HTTP_200_OK,
            summary="Login with username and password",
        )
        async def login(request: LoginRequest) -> LoginResponse:
            """
            Authenticate with username and password.

            Returns JWT access token and refresh token.
            """
            try:
                command = LoginCommand(
                    username=request.username, password=request.password
                )
                result = await self.auth_service.login(command)

                return LoginResponse(
                    access_token=result.access_token,
                    token_type=result.token_type,
                    expires_in=result.expires_in,
                    refresh_token=result.refresh_token,
                )

            except AuthenticationError as e:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)
                ) from e

        @router.post(
            "/refresh",
            response_model=LoginResponse,
            status_code=status.HTTP_200_OK,
            summary="Refresh access token",
        )
        async def refresh_token(request: RefreshTokenRequest) -> LoginResponse:
            """
            Refresh access token using refresh token.

            Returns new JWT access token and refresh token.
            """
            try:
                result = await self.auth_service.refresh_token(request.refresh_token)

                return LoginResponse(
                    access_token=result.access_token,
                    token_type=result.token_type,
                    expires_in=result.expires_in,
                    refresh_token=result.refresh_token,
                )

            except AuthenticationError as e:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)
                ) from e

        # ====================================================================
        # Authenticated Endpoints
        # ====================================================================

        @router.get(
            "/me",
            response_model=MeResponse,
            status_code=status.HTTP_200_OK,
            summary="Get current user info",
        )
        async def get_current_user_info(
            auth: AuthContext = Depends(self.auth_deps.get_current_user),
        ) -> MeResponse:
            """
            Get information about the currently authenticated user.

            Requires authentication (JWT token or API key).
            """
            return MeResponse(
                user_id=auth.user_id,
                username=auth.username,
                roles=list(auth.roles),
                permissions=[p.value for p in auth.permissions],
                auth_method=auth.auth_method,
            )

        # ====================================================================
        # User Management Endpoints (Admin Only)
        # ====================================================================

        @router.post(
            "/users",
            response_model=UserResponse,
            status_code=status.HTTP_201_CREATED,
            summary="Create a new user",
        )
        async def create_user(
            request: CreateUserRequest,
            _auth: AuthContext = Depends(
                self.auth_deps.require_permission(Permission.USER_CREATE)
            ),
        ) -> UserResponse:
            """
            Create a new user.

            Requires USER_CREATE permission (admin only).
            """
            try:
                command = CreateUserCommand(
                    username=request.username,
                    email=request.email,
                    password=request.password,
                    roles=set(request.roles),
                )
                user = await self.auth_service.create_user(command)

                return UserResponse(
                    id=user.id,
                    username=user.username,
                    email=user.email,
                    roles=list(user.roles),
                    is_active=user.is_active,
                    is_verified=user.is_verified,
                    created_at=user.created_at,
                    last_login_at=user.last_login_at,
                )

            except UserAlreadyExistsError as e:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=str(e)
                ) from e
            except ValidationError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
                ) from e

        @router.get(
            "/users/{user_id}",
            response_model=UserResponse,
            status_code=status.HTTP_200_OK,
            summary="Get user by ID",
        )
        async def get_user(
            user_id: UUID,
            _auth: AuthContext = Depends(
                self.auth_deps.require_permission(Permission.USER_VIEW)
            ),
        ) -> UserResponse:
            """
            Get user by ID.

            Requires USER_VIEW permission.
            """
            try:
                user = await self.auth_service.get_user(user_id)

                return UserResponse(
                    id=user.id,
                    username=user.username,
                    email=user.email,
                    roles=list(user.roles),
                    is_active=user.is_active,
                    is_verified=user.is_verified,
                    created_at=user.created_at,
                    last_login_at=user.last_login_at,
                )

            except UserNotFoundError as e:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
                ) from e

        @router.patch(
            "/users/{user_id}",
            response_model=UserResponse,
            status_code=status.HTTP_200_OK,
            summary="Update user",
        )
        async def update_user(
            user_id: UUID,
            request: UpdateUserRequest,
            _auth: AuthContext = Depends(
                self.auth_deps.require_permission(Permission.USER_UPDATE)
            ),
        ) -> UserResponse:
            """
            Update user.

            Requires USER_UPDATE permission (admin only).
            """
            try:
                command = UpdateUserCommand(
                    user_id=user_id,
                    email=request.email,
                    password=request.password,
                    roles=set(request.roles) if request.roles else None,
                    is_active=request.is_active,
                )
                user = await self.auth_service.update_user(command)

                return UserResponse(
                    id=user.id,
                    username=user.username,
                    email=user.email,
                    roles=list(user.roles),
                    is_active=user.is_active,
                    is_verified=user.is_verified,
                    created_at=user.created_at,
                    last_login_at=user.last_login_at,
                )

            except UserNotFoundError as e:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
                ) from e
            except ValidationError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
                ) from e

        @router.delete(
            "/users/{user_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Delete user",
        )
        async def delete_user(
            user_id: UUID,
            _auth: AuthContext = Depends(
                self.auth_deps.require_permission(Permission.USER_DELETE)
            ),
        ) -> None:
            """
            Delete user.

            Requires USER_DELETE permission (admin only).
            """
            try:
                await self.auth_service.delete_user(user_id)
            except UserNotFoundError as e:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
                ) from e

        # ====================================================================
        # API Key Management Endpoints
        # ====================================================================

        @router.post(
            "/api-keys",
            response_model=APIKeyResponse,
            status_code=status.HTTP_201_CREATED,
            summary="Create API key",
        )
        async def create_api_key(
            request: CreateAPIKeyRequest,
            auth: AuthContext = Depends(self.auth_deps.get_current_user),
        ) -> APIKeyResponse:
            """
            Create API key for the current user.

            Returns the API key only once - store it securely!
            """
            try:
                command = CreateAPIKeyCommand(
                    name=request.name,
                    user_id=auth.user_id,
                    roles=set(request.roles),
                    expires_at=request.expires_at,
                )
                api_key, plaintext_key = await self.auth_service.create_api_key(command)

                return APIKeyResponse(
                    id=api_key.id,
                    name=api_key.name,
                    key=plaintext_key,  # Only returned on creation
                    roles=list(api_key.roles),
                    is_active=api_key.is_active,
                    expires_at=api_key.expires_at,
                    created_at=api_key.created_at,
                    last_used_at=api_key.last_used_at,
                )

            except ValidationError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
                ) from e

        @router.get(
            "/api-keys",
            response_model=list[APIKeyResponse],
            status_code=status.HTTP_200_OK,
            summary="List API keys",
        )
        async def list_api_keys(
            auth: AuthContext = Depends(self.auth_deps.get_current_user),
        ) -> list[APIKeyResponse]:
            """
            List all API keys for the current user.
            """
            api_keys = await self.auth_service.list_api_keys(auth.user_id)

            return [
                APIKeyResponse(
                    id=key.id,
                    name=key.name,
                    key=None,  # Never return actual key
                    roles=list(key.roles),
                    is_active=key.is_active,
                    expires_at=key.expires_at,
                    created_at=key.created_at,
                    last_used_at=key.last_used_at,
                )
                for key in api_keys
            ]

        @router.delete(
            "/api-keys/{key_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Revoke API key",
        )
        async def revoke_api_key(
            key_id: UUID,
            _auth: AuthContext = Depends(self.auth_deps.get_current_user),
        ) -> None:
            """
            Revoke an API key.

            Users can only revoke their own API keys.
            Admins can revoke any API key.
            """
            # TODO: Add authorization check - users can only revoke their own keys
            await self.auth_service.revoke_api_key(key_id)

        return router
