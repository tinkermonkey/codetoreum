"""Authentication service for user authentication and authorization.

This module implements the authentication service that handles user login,
token generation, API key management, and permission checking.
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from codetoreum.domain.user import (
    ROLE_PERMISSIONS,
    APIKey,
    AuthContext,
    Permission,
    User,
    UserRole,
)
from codetoreum.ports.input.authentication import (
    APIKeyNotFoundError,
    AuthenticationError,
    CreateAPIKeyCommand,
    CreateUserCommand,
    IAuthenticationPort,
    LoginCommand,
    LoginResult,
    UpdateUserCommand,
    UserAlreadyExistsError,
    UserNotFoundError,
    ValidationError,
    validate_email,
    validate_password,
    validate_username,
)


class AuthenticationService(IAuthenticationPort):
    """Authentication service implementation.

    Handles user authentication, JWT token generation and validation,
    API key management, and permission checking.

    Attributes:
        user_repository: Repository for user persistence
        api_key_repository: Repository for API key persistence
        secret_key: Secret key for JWT signing
        algorithm: JWT algorithm (default: HS256)
        access_token_expire_minutes: Access token expiration in minutes
        refresh_token_expire_days: Refresh token expiration in days
        pwd_context: Passlib context for password hashing
    """

    def __init__(
        self,
        user_repository: "IUserRepository",
        api_key_repository: "IAPIKeyRepository",
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
    ):
        """Initialize authentication service.

        Args:
            user_repository: User repository
            api_key_repository: API key repository
            secret_key: Secret key for JWT signing
            algorithm: JWT algorithm
            access_token_expire_minutes: Access token expiration in minutes
            refresh_token_expire_days: Refresh token expiration in days
        """
        self.user_repo = user_repository
        self.api_key_repo = api_key_repository
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days

        # We use bcrypt directly (not passlib) for password hashing
        # to avoid compatibility issues with newer bcrypt versions

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt.

        Note: bcrypt has a maximum password length of 72 bytes.
        Passwords longer than this are truncated.
        """
        # Truncate to 72 bytes for bcrypt compatibility
        password_bytes = password.encode('utf-8')[:72]
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        # Return as string for consistency with existing code
        return hashed.decode('utf-8')

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash.

        Note: bcrypt has a maximum password length of 72 bytes.
        Passwords longer than this are truncated to match hashing behavior.
        """
        # Truncate to 72 bytes for bcrypt compatibility
        password_bytes = plain_password.encode('utf-8')[:72]
        # Convert hash string to bytes if needed
        if isinstance(hashed_password, str):
            hashed_bytes = hashed_password.encode('utf-8')
        else:
            hashed_bytes = hashed_password
        return bcrypt.checkpw(password_bytes, hashed_bytes)

    def _create_access_token(
        self, data: dict, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)

        to_encode.update({"exp": expire, "type": "access"})

        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def _create_refresh_token(
        self, data: dict, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a JWT refresh token."""
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)

        to_encode.update({"exp": expire, "type": "refresh"})

        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def _decode_token(self, token: str) -> dict:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError as e:
            msg = f"Invalid token: {e}"
            raise AuthenticationError(msg) from e

    async def create_user(self, command: CreateUserCommand) -> User:
        """Create a new user."""
        # Validate input
        validate_username(command.username)
        validate_email(command.email)
        validate_password(command.password)

        # Check if user already exists
        try:
            await self.user_repo.get_by_username(command.username)
            msg = f"User with username '{command.username}' already exists"
            raise UserAlreadyExistsError(msg)
        except UserNotFoundError:
            pass

        try:
            await self.user_repo.get_by_email(command.email)
            msg = f"User with email '{command.email}' already exists"
            raise UserAlreadyExistsError(msg)
        except UserNotFoundError:
            pass

        # Hash password
        hashed_password = self._hash_password(command.password)

        # Create user
        user = User(
            username=command.username,
            email=command.email,
            hashed_password=hashed_password,
            roles=command.roles,
            metadata=command.metadata or {},
        )

        # Save user
        await self.user_repo.save(user)

        return user

    async def update_user(self, command: UpdateUserCommand) -> User:
        """Update a user."""
        # Validate input
        if command.email is not None:
            validate_email(command.email)
        if command.password is not None:
            validate_password(command.password)

        # Get existing user
        user = await self.user_repo.get(command.user_id)

        # Update fields
        if command.email is not None:
            user.email = command.email

        if command.password is not None:
            user.update_password(self._hash_password(command.password))

        if command.roles is not None:
            user.roles = command.roles

        if command.is_active is not None:
            if command.is_active:
                user.activate()
            else:
                user.deactivate()

        if command.metadata is not None:
            user.metadata.update(command.metadata)

        user.updated_at = datetime.utcnow()

        # Save user
        await self.user_repo.save(user)

        return user

    async def get_user(self, user_id: UUID) -> User:
        """Get a user by ID."""
        return await self.user_repo.get(user_id)

    async def get_user_by_username(self, username: str) -> User:
        """Get a user by username."""
        return await self.user_repo.get_by_username(username)

    async def delete_user(self, user_id: UUID) -> None:
        """Delete a user."""
        await self.user_repo.delete(user_id)

    async def login(self, command: LoginCommand) -> LoginResult:
        """Authenticate a user with username and password."""
        # Get user
        try:
            user = await self.user_repo.get_by_username(command.username)
        except UserNotFoundError as e:
            msg = "Invalid username or password"
            raise AuthenticationError(msg) from e

        # Check if user is active
        if not user.is_active:
            msg = "User account is deactivated"
            raise AuthenticationError(msg)

        # Verify password
        if not self._verify_password(command.password, user.hashed_password):
            msg = "Invalid username or password"
            raise AuthenticationError(msg)

        # Record login
        user.record_login()
        await self.user_repo.save(user)

        # Create tokens
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "roles": [role.value for role in user.roles],
        }

        access_token = self._create_access_token(token_data)
        refresh_token = self._create_refresh_token({"sub": str(user.id)})

        return LoginResult(
            access_token=access_token,
            token_type="bearer",
            expires_in=self.access_token_expire_minutes * 60,
            refresh_token=refresh_token,
            user=user,
        )

    async def validate_token(self, token: str) -> AuthContext:
        """Validate a JWT token and return auth context."""
        payload = self._decode_token(token)

        # Check token type
        if payload.get("type") != "access":
            msg = "Invalid token type"
            raise AuthenticationError(msg)

        # Extract user info
        user_id = UUID(payload.get("sub"))
        username = payload.get("username")
        role_strings = payload.get("roles", [])

        # Convert role strings to enum
        roles = {UserRole(role) for role in role_strings}

        # Get permissions
        permissions: set[Permission] = set()
        for role in roles:
            permissions.update(ROLE_PERMISSIONS.get(role, set()))

        return AuthContext(
            user_id=user_id,
            username=username,
            roles=roles,
            permissions=permissions,
            auth_method="jwt",
        )

    async def refresh_token(self, refresh_token: str) -> LoginResult:
        """Refresh an access token using a refresh token."""
        payload = self._decode_token(refresh_token)

        # Check token type
        if payload.get("type") != "refresh":
            msg = "Invalid token type"
            raise AuthenticationError(msg)

        # Get user
        user_id = UUID(payload.get("sub"))
        user = await self.user_repo.get(user_id)

        # Check if user is active
        if not user.is_active:
            msg = "User account is deactivated"
            raise AuthenticationError(msg)

        # Create new tokens
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "roles": [role.value for role in user.roles],
        }

        access_token = self._create_access_token(token_data)
        new_refresh_token = self._create_refresh_token({"sub": str(user.id)})

        return LoginResult(
            access_token=access_token,
            token_type="bearer",
            expires_in=self.access_token_expire_minutes * 60,
            refresh_token=new_refresh_token,
            user=user,
        )

    async def create_api_key(self, command: CreateAPIKeyCommand) -> tuple[APIKey, str]:
        """Create a new API key."""
        # Verify user exists
        user = await self.user_repo.get(command.user_id)

        # Generate API key
        plaintext_key = f"ctk_{secrets.token_urlsafe(32)}"

        # Hash key for storage
        hashed_key = self._hash_password(plaintext_key)

        # Create API key object
        api_key = APIKey(
            key=hashed_key,
            name=command.name,
            user_id=user.id,
            roles=command.roles,
            expires_at=command.expires_at,
            metadata=command.metadata or {},
        )

        # Save API key
        await self.api_key_repo.save(api_key)

        return api_key, plaintext_key

    async def validate_api_key(self, key: str) -> AuthContext:
        """Validate an API key and return auth context."""
        # Get all active API keys (in production, this should be optimized)
        # For now, we'll implement a simple search
        all_keys = await self.api_key_repo.list_all()

        # Find matching key
        matched_key: Optional[APIKey] = None
        for api_key in all_keys:
            if self._verify_password(key, api_key.key):
                matched_key = api_key
                break

        if matched_key is None:
            msg = "Invalid API key"
            raise AuthenticationError(msg)

        # Check if key is valid
        if not matched_key.is_valid():
            msg = "API key is expired or revoked"
            raise AuthenticationError(msg)

        # Get user
        user = await self.user_repo.get(matched_key.user_id)

        # Check if user is active
        if not user.is_active:
            msg = "User account is deactivated"
            raise AuthenticationError(msg)

        # Record usage
        matched_key.record_usage()
        await self.api_key_repo.save(matched_key)

        # Get permissions
        permissions = matched_key.get_permissions()

        return AuthContext(
            user_id=user.id,
            username=user.username,
            roles=matched_key.roles,
            permissions=permissions,
            auth_method="api_key",
            api_key_id=matched_key.id,
        )

    async def revoke_api_key(self, key_id: UUID) -> None:
        """Revoke an API key."""
        api_key = await self.api_key_repo.get(key_id)
        api_key.revoke()
        await self.api_key_repo.save(api_key)

    async def list_api_keys(self, user_id: UUID) -> list[APIKey]:
        """List all API keys for a user."""
        return await self.api_key_repo.list_by_user(user_id)

    async def check_permission(self, auth_context: AuthContext, permission: str) -> bool:
        """Check if auth context has a specific permission."""
        try:
            perm = Permission(permission)
            return auth_context.has_permission(perm)
        except ValueError:
            return False


# Repository interfaces (to be implemented in secondary adapters)


class IUserRepository:
    """Repository interface for user persistence."""

    async def save(self, user: User) -> None:
        """Save a user."""
        raise NotImplementedError

    async def get(self, user_id: UUID) -> User:
        """Get a user by ID."""
        raise NotImplementedError

    async def get_by_username(self, username: str) -> User:
        """Get a user by username."""
        raise NotImplementedError

    async def get_by_email(self, email: str) -> User:
        """Get a user by email."""
        raise NotImplementedError

    async def delete(self, user_id: UUID) -> None:
        """Delete a user."""
        raise NotImplementedError


class IAPIKeyRepository:
    """Repository interface for API key persistence."""

    async def save(self, api_key: APIKey) -> None:
        """Save an API key."""
        raise NotImplementedError

    async def get(self, key_id: UUID) -> APIKey:
        """Get an API key by ID."""
        raise NotImplementedError

    async def list_by_user(self, user_id: UUID) -> list[APIKey]:
        """List all API keys for a user."""
        raise NotImplementedError

    async def list_all(self) -> list[APIKey]:
        """List all API keys (for validation)."""
        raise NotImplementedError

    async def delete(self, key_id: UUID) -> None:
        """Delete an API key."""
        raise NotImplementedError
