"""Integration tests for GitHub Ticket Adapter.

These tests interact with the actual GitHub API and are marked as integration tests.
They require a GitHub token to run.
"""

import os
from datetime import datetime, timezone

import pytest

from codetoreum.adapters.secondary import GitHubConfig, GitHubTicketAdapter
from codetoreum.domain.types import ProjectId, WorkItemId
from codetoreum.domain.work_item import WorkItemPriority, WorkItemStatus
from codetoreum.ports.exceptions import WorkItemNotFoundError


@pytest.fixture
def github_config():
    """Create GitHub configuration from environment."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        pytest.skip("GITHUB_TOKEN environment variable not set")

    # Use a test repository
    org = os.getenv("GITHUB_TEST_ORG", "test-org")
    repo = os.getenv("GITHUB_TEST_REPO", "test-repo")

    return GitHubConfig(
        token=token,
        organization=org,
        repository=repo,
        timeout_seconds=30,
    )


@pytest.fixture
async def github_adapter(github_config):
    """Create GitHub adapter instance."""
    adapter = GitHubTicketAdapter(github_config)
    yield adapter
    await adapter.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_work_item(github_adapter):
    """Test getting a work item by ID."""
    # This test assumes issue #1 exists in the test repository
    try:
        work_item = await github_adapter.get_work_item(WorkItemId("1"))

        assert work_item is not None
        assert work_item.id == WorkItemId("1")
        assert work_item.title
        assert isinstance(work_item.status, WorkItemStatus)
        assert isinstance(work_item.priority, WorkItemPriority)

    except WorkItemNotFoundError:
        pytest.skip("Test issue #1 not found in repository")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_work_items(github_adapter):
    """Test listing work items."""
    try:
        work_items = await github_adapter.list_work_items(limit=10)

        assert isinstance(work_items, list)
        # Repository may have no issues
        if work_items:
            assert all(hasattr(item, "id") for item in work_items)
            assert all(hasattr(item, "title") for item in work_items)
    except Exception as e:
        if "Not Found" in str(e) or "404" in str(e):
            pytest.skip("Test repository not found or not accessible")
        raise


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_work_items(github_adapter):
    """Test searching work items."""
    try:
        # Search for open issues
        results = await github_adapter.search_work_items("is:open", limit=10)

        assert isinstance(results, list)
    except Exception as e:
        if "Not Found" in str(e) or "404" in str(e) or "Validation Failed" in str(e) or "422" in str(e) or "do not exist" in str(e):
            pytest.skip("Test repository not found or not accessible")
        raise


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_update_work_item(github_adapter, github_config):
    """Test creating and updating a work item."""
    try:
        project_id = ProjectId(f"{github_config.organization}/{github_config.repository}")

        # Create work item
        work_item = await github_adapter.create_work_item(
            title="Test Issue - Integration Test",
            description="This is a test issue created by integration tests",
            project_id=project_id,
            labels=["test"],
            priority=WorkItemPriority.LOW,
        )

        assert work_item is not None
        assert work_item.id
        assert work_item.title == "Test Issue - Integration Test"
        assert "test" in work_item.labels

        # Update work item
        updated = await github_adapter.update_work_item(
            work_item.id,
            {"title": "Test Issue - Updated"},
        )

        assert updated.title == "Test Issue - Updated"

        # Add comment
        comment = await github_adapter.add_comment(
            work_item.id,
            "This is a test comment",
        )

        assert comment is not None
        assert comment.body == "This is a test comment"

        # Get comments
        comments = await github_adapter.get_comments(work_item.id)
        assert len(comments) >= 1

        # Close work item
        await github_adapter.update_status(
            work_item.id,
            WorkItemStatus.COMPLETED,
            "Test completed",
        )

        # Clean up - delete (close) the work item
        await github_adapter.delete_work_item(work_item.id)
    except Exception as e:
        if "Not Found" in str(e) or "404" in str(e):
            pytest.skip("Test repository not found or not accessible")
        raise


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhooks(github_adapter):
    """Test webhook registration and unregistration."""
    try:
        # Register webhook
        webhook_id = await github_adapter.register_webhook(
            url="https://example.com/webhook",
            events=["issues"],
        )

        assert webhook_id is not None

        # Unregister webhook
        await github_adapter.unregister_webhook(webhook_id)
    except Exception as e:
        if "Not Found" in str(e) or "404" in str(e):
            pytest.skip("Test repository not found or not accessible")
        raise


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_nonexistent_work_item(github_adapter):
    """Test getting a non-existent work item raises error."""
    with pytest.raises(WorkItemNotFoundError):
        await github_adapter.get_work_item(WorkItemId("999999999"))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_context_manager(github_config):
    """Test using adapter as async context manager."""
    try:
        async with GitHubTicketAdapter(github_config) as adapter:
            # Adapter should be usable
            items = await adapter.list_work_items(limit=1)
            assert isinstance(items, list)

        # Adapter should be closed after exiting context
    except Exception as e:
        if "Not Found" in str(e) or "404" in str(e):
            pytest.skip("Test repository not found or not accessible")
        raise
