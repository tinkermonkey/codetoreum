"""Unit tests for User domain model."""

import pytest
from uuid import UUID

from codetoreum.domain.user import (
    Permission,
    ROLE_PERMISSIONS,
    User,
    UserRole,
)


class TestUserRoleEnum:
    """Test UserRole enumeration."""

    def test_admin_role(self) -> None:
        """Test ADMIN role value."""
        assert UserRole.ADMIN.value == "admin"

    def test_developer_role(self) -> None:
        """Test DEVELOPER role value."""
        assert UserRole.DEVELOPER.value == "developer"

    def test_viewer_role(self) -> None:
        """Test VIEWER role value."""
        assert UserRole.VIEWER.value == "viewer"

    def test_service_account_role(self) -> None:
        """Test SERVICE_ACCOUNT role value."""
        assert UserRole.SERVICE_ACCOUNT.value == "service_account"


class TestPermissionEnum:
    """Test Permission enumeration."""

    def test_workflow_create_permission(self) -> None:
        """Test WORKFLOW_CREATE permission."""
        assert Permission.WORKFLOW_CREATE.value == "workflow:create"

    def test_workflow_view_permission(self) -> None:
        """Test WORKFLOW_VIEW permission."""
        assert Permission.WORKFLOW_VIEW.value == "workflow:view"

    def test_workflow_cancel_permission(self) -> None:
        """Test WORKFLOW_CANCEL permission."""
        assert Permission.WORKFLOW_CANCEL.value == "workflow:cancel"

    def test_execution_view_permission(self) -> None:
        """Test EXECUTION_VIEW permission."""
        assert Permission.EXECUTION_VIEW.value == "execution:view"

    def test_config_view_permission(self) -> None:
        """Test CONFIG_VIEW permission."""
        assert Permission.CONFIG_VIEW.value == "config:view"

    def test_project_permissions(self) -> None:
        """Test project permissions."""
        perms = [
            Permission.PROJECT_CREATE,
            Permission.PROJECT_VIEW,
            Permission.PROJECT_UPDATE,
            Permission.PROJECT_DELETE,
        ]
        assert len(perms) == 4


class TestRolePermissionsMapping:
    """Test role to permissions mapping."""

    def test_admin_has_all_permissions(self) -> None:
        """Test that admin role has all permissions."""
        admin_perms = ROLE_PERMISSIONS[UserRole.ADMIN]
        all_perms = set(Permission)
        assert admin_perms == all_perms

    def test_developer_permissions(self) -> None:
        """Test developer role permissions."""
        dev_perms = ROLE_PERMISSIONS[UserRole.DEVELOPER]
        assert Permission.WORKFLOW_CREATE in dev_perms
        assert Permission.WORKFLOW_VIEW in dev_perms
        assert Permission.EXECUTION_VIEW in dev_perms
        assert Permission.USER_DELETE not in dev_perms

    def test_viewer_permissions(self) -> None:
        """Test viewer role permissions."""
        viewer_perms = ROLE_PERMISSIONS[UserRole.VIEWER]
        assert Permission.WORKFLOW_VIEW in viewer_perms
        assert Permission.EXECUTION_VIEW in viewer_perms
        assert Permission.WORKFLOW_CREATE not in viewer_perms

    def test_service_account_permissions(self) -> None:
        """Test service account role permissions."""
        sa_perms = ROLE_PERMISSIONS[UserRole.SERVICE_ACCOUNT]
        assert Permission.WORKFLOW_CREATE in sa_perms
        assert Permission.USER_DELETE not in sa_perms


class TestUserCreation:
    """Test user creation and validation."""

    def test_create_valid_user(self) -> None:
        """Test creating a valid user."""
        user = User(
            username="john_doe",
            email="john@example.com",
            hashed_password="hashed_password_here",
            roles={UserRole.DEVELOPER},
        )

        assert user.username == "john_doe"
        assert user.email == "john@example.com"
        assert UserRole.DEVELOPER in user.roles
        assert isinstance(user.id, UUID)

    def test_create_user_with_defaults(self) -> None:
        """Test creating user with minimal required fields."""
        user = User(username="alice", email="alice@example.com", hashed_password="hash")

        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert UserRole.VIEWER in user.roles  # Default role
        assert user.is_active is True
        assert user.is_verified is False

    def test_missing_username(self) -> None:
        """Test that missing username raises ValueError."""
        with pytest.raises(ValueError, match="Username is required"):
            User(username="", email="user@example.com", hashed_password="hash")

    def test_missing_email(self) -> None:
        """Test that missing email raises ValueError."""
        with pytest.raises(ValueError, match="Email is required"):
            User(username="john", email="", hashed_password="hash")

    def test_invalid_email_format(self) -> None:
        """Test that invalid email format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid email address"):
            User(username="john", email="invalid-email", hashed_password="hash")

    def test_valid_email_formats(self) -> None:
        """Test various valid email formats."""
        valid_emails = [
            "user@example.com",
            "user.name@example.com",
            "user+tag@example.co.uk",
            "user123@test.org",
        ]

        for email in valid_emails:
            user = User(username="test", email=email, hashed_password="hash")
            assert user.email == email


class TestUserRoleManagement:
    """Test user role management methods."""

    def test_add_role(self) -> None:
        """Test adding a role to user."""
        user = User(username="john", email="john@example.com", hashed_password="hash")
        initial_count = len(user.roles)

        user.add_role(UserRole.DEVELOPER)

        assert UserRole.DEVELOPER in user.roles
        assert len(user.roles) == initial_count + 1

    def test_add_duplicate_role(self) -> None:
        """Test adding an already existing role."""
        user = User(
            username="john",
            email="john@example.com",
            hashed_password="hash",
            roles={UserRole.VIEWER},
        )
        initial_count = len(user.roles)

        user.add_role(UserRole.VIEWER)

        assert len(user.roles) == initial_count  # No change

    def test_remove_role(self) -> None:
        """Test removing a role from user."""
        user = User(
            username="john",
            email="john@example.com",
            hashed_password="hash",
            roles={UserRole.VIEWER, UserRole.DEVELOPER},
        )

        user.remove_role(UserRole.VIEWER)

        assert UserRole.VIEWER not in user.roles
        assert UserRole.DEVELOPER in user.roles

    def test_remove_nonexistent_role(self) -> None:
        """Test removing a role that user doesn't have."""
        user = User(
            username="john",
            email="john@example.com",
            hashed_password="hash",
            roles={UserRole.VIEWER},
        )
        initial_count = len(user.roles)

        user.remove_role(UserRole.ADMIN)  # Not in user's roles

        assert len(user.roles) == initial_count  # No change

    def test_has_role(self) -> None:
        """Test checking if user has a specific role."""
        user = User(
            username="john",
            email="john@example.com",
            hashed_password="hash",
            roles={UserRole.DEVELOPER},
        )

        assert user.has_role(UserRole.DEVELOPER)
        assert not user.has_role(UserRole.ADMIN)


class TestUserPermissionChecking:
    """Test user permission checking."""

    def test_admin_has_all_permissions(self) -> None:
        """Test that admin user has all permissions."""
        admin = User(
            username="admin",
            email="admin@example.com",
            hashed_password="hash",
            roles={UserRole.ADMIN},
        )

        for permission in Permission:
            assert admin.has_permission(permission)

    def test_developer_has_expected_permissions(self) -> None:
        """Test developer user has expected permissions."""
        dev = User(
            username="dev",
            email="dev@example.com",
            hashed_password="hash",
            roles={UserRole.DEVELOPER},
        )

        assert dev.has_permission(Permission.WORKFLOW_CREATE)
        assert dev.has_permission(Permission.EXECUTION_VIEW)
        assert not dev.has_permission(Permission.USER_DELETE)

    def test_viewer_has_read_only_permissions(self) -> None:
        """Test viewer user has only read permissions."""
        viewer = User(
            username="viewer",
            email="viewer@example.com",
            hashed_password="hash",
            roles={UserRole.VIEWER},
        )

        assert viewer.has_permission(Permission.WORKFLOW_VIEW)
        assert viewer.has_permission(Permission.EXECUTION_VIEW)
        assert not viewer.has_permission(Permission.WORKFLOW_CREATE)

    def test_service_account_permissions(self) -> None:
        """Test service account has API permissions."""
        sa = User(
            username="bot",
            email="bot@example.com",
            hashed_password="hash",
            roles={UserRole.SERVICE_ACCOUNT},
        )

        assert sa.has_permission(Permission.WORKFLOW_CREATE)
        assert sa.has_permission(Permission.EXECUTION_VIEW)
        assert not sa.has_permission(Permission.USER_DELETE)

    def test_multiple_roles_permission_union(self) -> None:
        """Test that user with multiple roles has union of permissions."""
        user = User(
            username="multi",
            email="multi@example.com",
            hashed_password="hash",
            roles={UserRole.DEVELOPER, UserRole.VIEWER},
        )

        # Should have both developer and viewer permissions
        assert user.has_permission(Permission.WORKFLOW_CREATE)  # Developer
        assert user.has_permission(Permission.WORKFLOW_VIEW)  # Viewer


class TestUserMetadata:
    """Test user metadata handling."""

    def test_user_with_metadata(self) -> None:
        """Test creating user with metadata."""
        metadata = {"department": "engineering", "manager": "jane"}
        user = User(
            username="john",
            email="john@example.com",
            hashed_password="hash",
            metadata=metadata,
        )

        assert user.metadata == metadata
        assert user.metadata["department"] == "engineering"

    def test_user_empty_metadata(self) -> None:
        """Test user with empty metadata."""
        user = User(username="john", email="john@example.com", hashed_password="hash")
        assert user.metadata == {}

    def test_user_metadata_modification(self) -> None:
        """Test modifying user metadata."""
        user = User(username="john", email="john@example.com", hashed_password="hash")

        user.metadata["key"] = "value"
        assert user.metadata["key"] == "value"


class TestUserTimestamps:
    """Test user timestamp handling."""

    def test_user_created_at(self) -> None:
        """Test user has created_at timestamp."""
        user = User(username="john", email="john@example.com", hashed_password="hash")
        assert user.created_at is not None

    def test_user_updated_at(self) -> None:
        """Test user has updated_at timestamp."""
        user = User(username="john", email="john@example.com", hashed_password="hash")
        assert user.updated_at is not None

    def test_user_last_login_at_none(self) -> None:
        """Test user last_login_at is None initially."""
        user = User(username="john", email="john@example.com", hashed_password="hash")
        assert user.last_login_at is None

    def test_updated_at_changes_on_role_change(self) -> None:
        """Test that updated_at changes when role is modified."""
        user = User(username="john", email="john@example.com", hashed_password="hash")
        initial_updated_at = user.updated_at

        # Small delay to ensure timestamp difference
        import time
        time.sleep(0.01)

        user.add_role(UserRole.ADMIN)

        assert user.updated_at > initial_updated_at


class TestUserIsActive:
    """Test user active status."""

    def test_user_active_by_default(self) -> None:
        """Test that user is active by default."""
        user = User(username="john", email="john@example.com", hashed_password="hash")
        assert user.is_active is True

    def test_user_inactive(self) -> None:
        """Test creating inactive user."""
        user = User(
            username="john",
            email="john@example.com",
            hashed_password="hash",
            is_active=False,
        )
        assert user.is_active is False


class TestUserVerification:
    """Test user verification status."""

    def test_user_unverified_by_default(self) -> None:
        """Test that user is unverified by default."""
        user = User(username="john", email="john@example.com", hashed_password="hash")
        assert user.is_verified is False

    def test_user_verified(self) -> None:
        """Test creating verified user."""
        user = User(
            username="john",
            email="john@example.com",
            hashed_password="hash",
            is_verified=True,
        )
        assert user.is_verified is True
