"""User domain model for authentication and authorization.

This module defines the User entity and related value objects for
authentication and authorization in the Codetoreum system.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class UserRole(str, Enum):
    """User roles for RBAC."""

    ADMIN = "admin"  # Full system access
    DEVELOPER = "developer"  # Can trigger workflows, view executions
    VIEWER = "viewer"  # Read-only access
    SERVICE_ACCOUNT = "service_account"  # API access only


class Permission(str, Enum):
    """Granular permissions for authorization."""

    # Workflow permissions
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_VIEW = "workflow:view"
    WORKFLOW_CANCEL = "workflow:cancel"
    WORKFLOW_RETRY = "workflow:retry"

    # Execution permissions
    EXECUTION_VIEW = "execution:view"
    EXECUTION_CANCEL = "execution:cancel"

    # Configuration permissions
    CONFIG_VIEW = "config:view"
    CONFIG_UPDATE = "config:update"

    # Project permissions
    PROJECT_CREATE = "project:create"
    PROJECT_VIEW = "project:view"
    PROJECT_UPDATE = "project:update"
    PROJECT_DELETE = "project:delete"

    # User permissions
    USER_CREATE = "user:create"
    USER_VIEW = "user:view"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"


# Role to permissions mapping
ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.ADMIN: set(Permission),  # All permissions
    UserRole.DEVELOPER: {
        Permission.WORKFLOW_CREATE,
        Permission.WORKFLOW_VIEW,
        Permission.WORKFLOW_CANCEL,
        Permission.WORKFLOW_RETRY,
        Permission.EXECUTION_VIEW,
        Permission.EXECUTION_CANCEL,
        Permission.CONFIG_VIEW,
        Permission.PROJECT_VIEW,
    },
    UserRole.VIEWER: {
        Permission.WORKFLOW_VIEW,
        Permission.EXECUTION_VIEW,
        Permission.CONFIG_VIEW,
        Permission.PROJECT_VIEW,
    },
    UserRole.SERVICE_ACCOUNT: {
        Permission.WORKFLOW_CREATE,
        Permission.WORKFLOW_VIEW,
        Permission.EXECUTION_VIEW,
        Permission.CONFIG_VIEW,
    },
}


@dataclass
class User:
    """User entity for authentication and authorization.

    Represents a user in the system with credentials, roles, and permissions.

    Attributes:
        id: Unique user identifier
        username: Unique username
        email: User email address
        hashed_password: Bcrypt hashed password
        roles: User roles for RBAC
        is_active: Whether user account is active
        is_verified: Whether email is verified
        created_at: User creation timestamp
        updated_at: Last update timestamp
        last_login_at: Last login timestamp
        metadata: Additional user metadata
    """

    id: UUID = field(default_factory=uuid4)
    username: str = field(default="")
    email: str = field(default="")
    hashed_password: str = field(default="", repr=False)
    roles: set[UserRole] = field(default_factory=set)
    is_active: bool = field(default=True)
    is_verified: bool = field(default=False)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_login_at: Optional[datetime] = field(default=None)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate user data after initialization."""
        if not self.username:
            msg = "Username is required"
            raise ValueError(msg)

        if not self.email:
            msg = "Email is required"
            raise ValueError(msg)

        if "@" not in self.email:
            msg = f"Invalid email address: {self.email}"
            raise ValueError(msg)

        if not self.roles:
            # Default to viewer role
            self.roles = {UserRole.VIEWER}

    def add_role(self, role: UserRole) -> None:
        """Add a role to the user."""
        self.roles.add(role)
        self.updated_at = datetime.now(timezone.utc)

    def remove_role(self, role: UserRole) -> None:
        """Remove a role from the user."""
        if role in self.roles:
            self.roles.remove(role)
            self.updated_at = datetime.now(timezone.utc)

    def has_role(self, role: UserRole) -> bool:
        """Check if user has a specific role."""
        return role in self.roles

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        # Check if any of the user's roles grant this permission
        for role in self.roles:
            if permission in ROLE_PERMISSIONS.get(role, set()):
                return True
        return False

    def get_permissions(self) -> set[Permission]:
        """Get all permissions for the user's roles."""
        permissions: set[Permission] = set()
        for role in self.roles:
            permissions.update(ROLE_PERMISSIONS.get(role, set()))
        return permissions

    def deactivate(self) -> None:
        """Deactivate user account."""
        self.is_active = False
        self.updated_at = datetime.now(timezone.utc)

    def activate(self) -> None:
        """Activate user account."""
        self.is_active = True
        self.updated_at = datetime.now(timezone.utc)

    def verify_email(self) -> None:
        """Mark email as verified."""
        self.is_verified = True
        self.updated_at = datetime.now(timezone.utc)

    def record_login(self) -> None:
        """Record user login timestamp."""
        self.last_login_at = datetime.now(timezone.utc)

    def update_password(self, hashed_password: str) -> None:
        """Update user password."""
        self.hashed_password = hashed_password
        self.updated_at = datetime.now(timezone.utc)


@dataclass
class APIKey:
    """API key for service account authentication.

    Represents an API key for programmatic access to the system.

    Attributes:
        id: Unique API key identifier
        key: API key string (hashed)
        name: Human-readable name for the key
        user_id: User ID this key belongs to
        roles: Roles granted to this key
        is_active: Whether key is active
        expires_at: Key expiration timestamp
        created_at: Key creation timestamp
        last_used_at: Last usage timestamp
        metadata: Additional key metadata
    """

    id: UUID = field(default_factory=uuid4)
    key: str = field(default="", repr=False)
    name: str = field(default="")
    user_id: UUID = field(default_factory=uuid4)
    roles: set[UserRole] = field(default_factory=set)
    is_active: bool = field(default=True)
    expires_at: Optional[datetime] = field(default=None)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = field(default=None)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate API key data after initialization."""
        if not self.name:
            msg = "API key name is required"
            raise ValueError(msg)

        if not self.key:
            msg = "API key is required"
            raise ValueError(msg)

        if not self.roles:
            # Default to service account role
            self.roles = {UserRole.SERVICE_ACCOUNT}

    def is_expired(self) -> bool:
        """Check if API key is expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def is_valid(self) -> bool:
        """Check if API key is valid (active and not expired)."""
        return self.is_active and not self.is_expired()

    def record_usage(self) -> None:
        """Record API key usage timestamp."""
        self.last_used_at = datetime.now(timezone.utc)

    def revoke(self) -> None:
        """Revoke API key."""
        self.is_active = False

    def get_permissions(self) -> set[Permission]:
        """Get all permissions for the API key's roles."""
        permissions: set[Permission] = set()
        for role in self.roles:
            permissions.update(ROLE_PERMISSIONS.get(role, set()))
        return permissions


@dataclass
class AuthContext:
    """Authentication context for a request.

    Contains information about the authenticated user or API key.

    Attributes:
        user_id: Authenticated user ID
        username: Authenticated username
        roles: User roles
        permissions: User permissions
        auth_method: Authentication method used (jwt, api_key, session)
        api_key_id: API key ID if authenticated via API key
        metadata: Additional context metadata
    """

    user_id: UUID
    username: str
    roles: set[UserRole]
    permissions: set[Permission]
    auth_method: str = "jwt"  # jwt, api_key, session
    api_key_id: Optional[UUID] = None
    metadata: dict = field(default_factory=dict)

    def has_permission(self, permission: Permission) -> bool:
        """Check if context has a specific permission."""
        return permission in self.permissions

    def has_role(self, role: UserRole) -> bool:
        """Check if context has a specific role."""
        return role in self.roles

    def is_admin(self) -> bool:
        """Check if context has admin role."""
        return UserRole.ADMIN in self.roles
