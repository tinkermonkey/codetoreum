"""Integration tests for GitHubCodeReviewAdapter.

Tests verify:
- PR status queries via GraphQL
- Event emission on status changes and comment additions
- Webhook processing for pull_request_review and pull_request events
- Polling fallback for change detection
- Status computation from GitHub review states
- Work item linkage and caching
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.secondary.github_code_review_adapter import (
    GitHubCodeReviewAdapter,
)
from codetoreum.adapters.secondary.github_ticket_adapter import GitHubTicketAdapter
from codetoreum.domain.events.review_events import (
    ReviewCommentAddedEvent,
    ReviewStatusChangedEvent,
)
from codetoreum.infrastructure.http.github_graphql_client import (
    GitHubGraphQLClient,
    GitHubGraphQLConfig,
)
from codetoreum.ports.exceptions import (
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.monitoring import MonitoringConfig, MonitoringState


class MockGraphQLClient:
    """Mock GraphQL client for testing without real GitHub API calls."""

    def __init__(self):
        self.queries: List[tuple] = []
        self.responses: Dict[str, Any] = {}
        self.call_count: Dict[str, int] = {}  # Track call counts per query type

    async def execute(self, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
        """Record query and return mock response."""
        self.queries.append((query, variables))

        # Return mock responses based on query type
        # Check for GetPullRequestComments FIRST since it contains "GetPullRequest"
        if "GetPullRequestComments" in query:
            return self.responses.get("GetPullRequestComments", {
                "node": {
                    "id": "PR123",
                    "reviews": {"nodes": []},
                    "comments": {"nodes": []},
                }
            })

        if "GetPullRequest" in query and "prId" in str(variables):
            # Track call count to simulate status changes after mutations
            query_type = "GetPullRequest"
            self.call_count[query_type] = self.call_count.get(query_type, 0) + 1

            # If we have a custom response sequence, use that
            if f"{query_type}_responses" in self.responses:
                responses_list = self.responses[f"{query_type}_responses"]
                call_idx = min(self.call_count[query_type] - 1, len(responses_list) - 1)
                return responses_list[call_idx]

            # Otherwise use default or single response
            return self.responses.get("GetPullRequest", {
                "node": {
                    "id": "PR123",
                    "state": "OPEN",
                    "isDraft": False,
                    "reviews": {
                        "nodes": [
                            {
                                "id": "REVIEW1",
                                "state": "APPROVED",
                                "author": {"login": "reviewer1"},
                                "submittedAt": "2024-01-01T10:00:00Z",
                            }
                        ]
                    },
                }
            })

        if "SearchPullRequests" in query:
            return self.responses.get("SearchPullRequests", {
                "search": {"nodes": []}
            })

        if "GetOpenPRs" in query:
            return self.responses.get("GetOpenPRs", {
                "repository": {
                    "pullRequests": {"nodes": []}
                }
            })

        if "SubmitReview" in query:
            return self.responses.get("SubmitReview", {
                "submitPullRequestReview": {
                    "pullRequestReview": {
                        "id": "REVIEW_NEW",
                        "state": "CHANGES_REQUESTED",
                        "author": {"login": "bot"},
                        "submittedAt": "2024-01-01T11:00:00Z",
                    }
                }
            })

        return {}

    async def close(self) -> None:
        """Close client."""
        pass


class MockTicketAdapter:
    """Mock ticket adapter for testing."""

    def __init__(self):
        self._owner = "test-owner"
        self._repo = "test-repo"


@pytest.fixture
def mock_graphql_client():
    """Provide mock GraphQL client."""
    return MockGraphQLClient()


@pytest.fixture
def mock_ticket_adapter():
    """Provide mock ticket adapter."""
    return MockTicketAdapter()


@pytest.fixture
def adapter(mock_graphql_client, mock_ticket_adapter):
    """Provide GitHubCodeReviewAdapter instance."""
    return GitHubCodeReviewAdapter(
        ticket_adapter=mock_ticket_adapter,
        graphql_client=mock_graphql_client,
        webhook_enabled=True,
    )


class TestEventEmitter:
    """Test IEventEmitter implementation."""

    def test_on_registers_handler(self, adapter):
        """Test registering event handler."""
        handler = MagicMock()
        adapter.on("review.status_changed", handler)

        assert "review.status_changed" in adapter._event_handlers
        assert handler in adapter._event_handlers["review.status_changed"]

    def test_off_unregisters_handler(self, adapter):
        """Test unregistering event handler."""
        handler = MagicMock()
        adapter.on("review.status_changed", handler)
        adapter.off("review.status_changed", handler)

        assert handler not in adapter._event_handlers.get("review.status_changed", [])

    def test_off_raises_on_not_subscribed(self, adapter):
        """Test unregister raises when handler not subscribed."""
        handler = MagicMock()

        with pytest.raises(ValueError):
            adapter.off("review.status_changed", handler)

    def test_emit_calls_handlers(self, adapter):
        """Test emitting event calls all handlers."""
        handler1 = MagicMock()
        handler2 = MagicMock()

        adapter.on("review.status_changed", handler1)
        adapter.on("review.status_changed", handler2)

        event = ReviewStatusChangedEvent(
            type="review.status_changed",
            timestamp="2024-01-01T10:00:00Z",
            source="github",
            review_id="PR123",
            project_id="proj-1",
            previous_status="open",
            new_status="approved",
        )

        adapter.emit(event)

        handler1.assert_called_once_with(event)
        handler2.assert_called_once_with(event)

    def test_emit_ignores_handler_errors(self, adapter):
        """Test emit continues on handler error."""
        handler1 = MagicMock(side_effect=Exception("Handler error"))
        handler2 = MagicMock()

        adapter.on("review.status_changed", handler1)
        adapter.on("review.status_changed", handler2)

        event = ReviewStatusChangedEvent(
            type="review.status_changed",
            timestamp="2024-01-01T10:00:00Z",
            source="github",
            review_id="PR123",
            project_id="proj-1",
            previous_status="open",
            new_status="approved",
        )

        adapter.emit(event)

        handler1.assert_called_once()
        handler2.assert_called_once()

    def test_on_rejects_non_callable(self, adapter):
        """Test on() rejects non-callable handlers."""
        with pytest.raises(ValueError, match="must be callable"):
            adapter.on("review.status_changed", "not-callable")


class TestMonitoringLifecycle:
    """Test IMonitoredService implementation."""

    @pytest.mark.asyncio
    async def test_start_monitoring_creates_status(self, adapter):
        """Test start_monitoring initializes monitoring status."""
        config = MonitoringConfig(project_id="proj-1")
        await adapter.start_monitoring("proj-1", config)

        status = await adapter.get_monitoring_status("proj-1")
        assert status.state == MonitoringState.ACTIVE
        assert status.project_id == "proj-1"
        assert status.started_at is not None

    @pytest.mark.asyncio
    async def test_stop_monitoring_sets_stopped(self, adapter):
        """Test stop_monitoring stops monitoring."""
        config = MonitoringConfig(project_id="proj-1")
        await adapter.start_monitoring("proj-1", config)
        await adapter.stop_monitoring("proj-1")

        status = await adapter.get_monitoring_status("proj-1")
        assert status.state == MonitoringState.STOPPED

    @pytest.mark.asyncio
    async def test_start_monitoring_without_webhook_starts_polling(self, mock_graphql_client, mock_ticket_adapter):
        """Test polling task starts when webhook disabled."""
        adapter = GitHubCodeReviewAdapter(
            ticket_adapter=mock_ticket_adapter,
            graphql_client=mock_graphql_client,
            webhook_enabled=False,
        )

        config = MonitoringConfig(project_id="proj-1")
        await adapter.start_monitoring("proj-1", config)

        assert "proj-1" in adapter._polling_tasks
        assert isinstance(adapter._polling_tasks["proj-1"], asyncio.Task)

        await adapter.stop_monitoring("proj-1")

    @pytest.mark.asyncio
    async def test_start_monitoring_validates_project_id(self, adapter):
        """Test start_monitoring validates project_id."""
        config = MonitoringConfig(project_id="")

        with pytest.raises(ValidationError):
            await adapter.start_monitoring("", config)

    @pytest.mark.asyncio
    async def test_stop_monitoring_validates_project_id(self, adapter):
        """Test stop_monitoring validates project_id."""
        with pytest.raises(ValidationError):
            await adapter.stop_monitoring("")

    @pytest.mark.asyncio
    async def test_stop_monitoring_not_started_raises(self, adapter):
        """Test stop_monitoring raises when not monitoring."""
        with pytest.raises(ResourceNotFoundError):
            await adapter.stop_monitoring("proj-999")

    @pytest.mark.asyncio
    async def test_stop_monitoring_cancels_polling_task(self, mock_graphql_client, mock_ticket_adapter):
        """Test stop_monitoring cancels polling task."""
        adapter = GitHubCodeReviewAdapter(
            ticket_adapter=mock_ticket_adapter,
            graphql_client=mock_graphql_client,
            webhook_enabled=False,
        )

        config = MonitoringConfig(project_id="proj-1")
        await adapter.start_monitoring("proj-1", config)

        task = adapter._polling_tasks["proj-1"]
        assert not task.done()

        await adapter.stop_monitoring("proj-1")

        # Give task time to handle cancellation
        await asyncio.sleep(0.1)
        assert task.done()


class TestQueryOperations:
    """Test query operations."""

    @pytest.mark.asyncio
    async def test_get_review_status_returns_approved(self, adapter, mock_graphql_client):
        """Test get_review_status returns approved status."""
        mock_graphql_client.responses["GetPullRequest"] = {
            "node": {
                "id": "PR123",
                "state": "OPEN",
                "reviews": {
                    "nodes": [
                        {
                            "state": "APPROVED",
                            "author": {"login": "reviewer1"},
                        }
                    ]
                },
            }
        }

        status = await adapter.get_review_status("PR123")
        assert status == "approved"

    @pytest.mark.asyncio
    async def test_get_review_status_returns_changes_requested(self, adapter, mock_graphql_client):
        """Test get_review_status returns changes_requested when any review requests changes."""
        mock_graphql_client.responses["GetPullRequest"] = {
            "node": {
                "id": "PR123",
                "state": "OPEN",
                "reviews": {
                    "nodes": [
                        {"state": "APPROVED", "author": {"login": "reviewer1"}},
                        {"state": "CHANGES_REQUESTED", "author": {"login": "reviewer2"}},
                    ]
                },
            }
        }

        status = await adapter.get_review_status("PR123")
        assert status == "changes_requested"

    @pytest.mark.asyncio
    async def test_get_review_status_returns_merged(self, adapter, mock_graphql_client):
        """Test get_review_status returns merged for merged PRs."""
        mock_graphql_client.responses["GetPullRequest"] = {
            "node": {
                "id": "PR123",
                "state": "MERGED",
                "reviews": {"nodes": []},
            }
        }

        status = await adapter.get_review_status("PR123")
        assert status == "merged"

    @pytest.mark.asyncio
    async def test_get_review_status_returns_closed(self, adapter, mock_graphql_client):
        """Test get_review_status returns closed for closed PRs."""
        mock_graphql_client.responses["GetPullRequest"] = {
            "node": {
                "id": "PR123",
                "state": "CLOSED",
                "reviews": {"nodes": []},
            }
        }

        status = await adapter.get_review_status("PR123")
        assert status == "closed"

    @pytest.mark.asyncio
    async def test_get_review_status_not_found_raises(self, adapter, mock_graphql_client):
        """Test get_review_status raises when PR not found."""
        mock_graphql_client.responses["GetPullRequest"] = {"node": None}

        with pytest.raises(ResourceNotFoundError):
            await adapter.get_review_status("PR999")

    @pytest.mark.asyncio
    async def test_get_review_status_validates_review_id(self, adapter):
        """Test get_review_status validates review_id."""
        with pytest.raises(ValidationError):
            await adapter.get_review_status("")

    @pytest.mark.asyncio
    async def test_get_review_comments_returns_all_comments(self, adapter, mock_graphql_client):
        """Test get_review_comments returns all types of comments."""
        mock_graphql_client.responses["GetPullRequestComments"] = {
            "node": {
                "id": "PR123",
                "reviews": {
                    "nodes": [
                        {
                            "id": "REVIEW1",
                            "body": "Review body",
                            "author": {"login": "reviewer1"},
                            "submittedAt": "2024-01-01T10:00:00Z",
                            "comments": {
                                "nodes": [
                                    {
                                        "id": "COMMENT1",
                                        "body": "Inline comment",
                                        "author": {"login": "reviewer1"},
                                        "createdAt": "2024-01-01T10:00:00Z",
                                        "path": "src/main.py",
                                        "position": 42,
                                    }
                                ]
                            },
                        }
                    ]
                },
                "comments": {
                    "nodes": [
                        {
                            "id": "COMMENT2",
                            "body": "Discussion comment",
                            "author": {"login": "author"},
                            "createdAt": "2024-01-01T10:30:00Z",
                        }
                    ]
                },
            }
        }

        comments = await adapter.get_review_comments("PR123")

        assert len(comments) == 3
        assert comments[0].body == "Review body"
        assert comments[1].body == "Inline comment"
        assert comments[2].body == "Discussion comment"


class TestCommandOperations:
    """Test command operations."""

    @pytest.mark.asyncio
    async def test_request_changes_emits_status_changed(self, adapter, mock_graphql_client):
        """Test request_changes emits review.status_changed event."""
        # First call returns no reviews (initial state), second call returns the new review
        mock_graphql_client.responses["GetPullRequest_responses"] = [
            {
                "node": {
                    "id": "PR123",
                    "state": "OPEN",
                    "reviews": {"nodes": []},
                }
            },
            {
                "node": {
                    "id": "PR123",
                    "state": "OPEN",
                    "reviews": {
                        "nodes": [
                            {
                                "id": "REVIEW_NEW",
                                "state": "CHANGES_REQUESTED",
                                "author": {"login": "bot"},
                                "submittedAt": "2024-01-01T11:00:00Z",
                            }
                        ]
                    },
                }
            },
        ]

        # Mock response after mutation
        mock_graphql_client.responses["SubmitReview"] = {
            "submitPullRequestReview": {
                "pullRequestReview": {
                    "id": "REVIEW_NEW",
                    "state": "CHANGES_REQUESTED",
                    "author": {"login": "bot"},
                    "submittedAt": "2024-01-01T11:00:00Z",
                }
            }
        }

        events = []
        adapter.on("review.status_changed", events.append)

        await adapter.request_changes("PR123", "Please fix X")

        # Should emit status_changed event
        assert len(events) >= 1
        assert events[0].type == "review.status_changed"
        assert events[0].new_status == "changes_requested"

    @pytest.mark.asyncio
    async def test_request_changes_emits_comment_added(self, adapter, mock_graphql_client):
        """Test request_changes emits review.comment_added event."""
        # First call returns no reviews (initial state), second call returns the new review
        mock_graphql_client.responses["GetPullRequest_responses"] = [
            {
                "node": {
                    "id": "PR123",
                    "state": "OPEN",
                    "reviews": {"nodes": []},
                }
            },
            {
                "node": {
                    "id": "PR123",
                    "state": "OPEN",
                    "reviews": {
                        "nodes": [
                            {
                                "id": "REVIEW_NEW",
                                "state": "CHANGES_REQUESTED",
                                "author": {"login": "bot"},
                                "submittedAt": "2024-01-01T11:00:00Z",
                            }
                        ]
                    },
                }
            },
        ]

        mock_graphql_client.responses["SubmitReview"] = {
            "submitPullRequestReview": {
                "pullRequestReview": {
                    "id": "REVIEW_NEW",
                    "state": "CHANGES_REQUESTED",
                    "author": {"login": "bot"},
                    "submittedAt": "2024-01-01T11:00:00Z",
                }
            }
        }

        events = []
        adapter.on("review.comment_added", events.append)

        await adapter.request_changes("PR123", "Please fix X")

        # Should emit comment_added event
        assert len(events) >= 1
        assert events[0].type == "review.comment_added"
        assert events[0].comment.body == "Please fix X"

    @pytest.mark.asyncio
    async def test_request_changes_validates_review_id(self, adapter):
        """Test request_changes validates review_id."""
        with pytest.raises(ValidationError):
            await adapter.request_changes("", "Please fix X")

    @pytest.mark.asyncio
    async def test_request_changes_validates_comments(self, adapter):
        """Test request_changes validates comments."""
        with pytest.raises(ValidationError):
            await adapter.request_changes("PR123", "")

    @pytest.mark.asyncio
    async def test_request_changes_rejects_too_long_comments(self, adapter):
        """Test request_changes rejects too-long comments."""
        too_long = "x" * 100000

        with pytest.raises(ValidationError):
            await adapter.request_changes("PR123", too_long)

    @pytest.mark.asyncio
    async def test_approve_emits_status_changed(self, adapter, mock_graphql_client):
        """Test approve emits review.status_changed event."""
        # First call returns no reviews (initial state), second call returns the approval
        mock_graphql_client.responses["GetPullRequest_responses"] = [
            {
                "node": {
                    "id": "PR123",
                    "state": "OPEN",
                    "reviews": {"nodes": []},
                }
            },
            {
                "node": {
                    "id": "PR123",
                    "state": "OPEN",
                    "reviews": {
                        "nodes": [
                            {
                                "id": "REVIEW_NEW",
                                "state": "APPROVED",
                                "author": {"login": "bot"},
                                "submittedAt": "2024-01-01T11:00:00Z",
                            }
                        ]
                    },
                }
            },
        ]

        mock_graphql_client.responses["SubmitReview"] = {
            "submitPullRequestReview": {
                "pullRequestReview": {
                    "id": "REVIEW_NEW",
                    "state": "APPROVED",
                    "author": {"login": "bot"},
                    "submittedAt": "2024-01-01T11:00:00Z",
                }
            }
        }

        events = []
        adapter.on("review.status_changed", events.append)

        await adapter.approve("PR123")

        # Should emit status_changed event
        assert len(events) >= 1
        assert events[0].type == "review.status_changed"
        assert events[0].new_status == "approved"


class TestWebhookHandling:
    """Test webhook event handling."""

    @pytest.mark.asyncio
    async def test_handle_webhook_review_submitted(self, adapter):
        """Test handling pull_request_review submitted event."""
        payload = {
            "action": "submitted",
            "review": {
                "id": "REVIEW123",
                "state": "APPROVED",
                "user": {"login": "reviewer1"},
                "submittedAt": "2024-01-01T10:00:00Z",
            },
            "pull_request": {
                "id": 456,
                "title": "Test PR",
                "body": "PR body",
                "headRefName": "feature/item-123",
                "baseRefName": "main",
            },
            "repository": {
                "owner": {"login": "test-owner"},
                "name": "test-repo",
            },
        }

        events = []
        adapter.on("review.status_changed", events.append)

        await adapter.handle_webhook(payload)

        # First call initializes status, so no event yet
        # But subsequent calls should emit

    @pytest.mark.asyncio
    async def test_handle_webhook_pr_merged(self, adapter):
        """Test handling pull_request merged event."""
        payload = {
            "action": "merged",
            "pull_request": {
                "id": 456,
                "title": "Test PR",
                "body": "PR body",
                "headRefName": "feature/item-123",
                "baseRefName": "main",
                "state": "MERGED",
            },
            "repository": {
                "owner": {"login": "test-owner"},
                "name": "test-repo",
            },
        }

        # Set initial status so we can detect change
        adapter._last_known_status["456"] = "open"

        events = []
        adapter.on("review.status_changed", events.append)

        await adapter.handle_webhook(payload)

        # Should emit status_changed event
        assert len(events) >= 1
        assert events[0].type == "review.status_changed"
        assert events[0].new_status == "merged"

    @pytest.mark.asyncio
    async def test_handle_webhook_pr_closed(self, adapter):
        """Test handling pull_request closed event."""
        payload = {
            "action": "closed",
            "pull_request": {
                "id": 456,
                "title": "Test PR",
                "body": "PR body",
                "headRefName": "feature/item-123",
                "baseRefName": "main",
                "state": "CLOSED",
            },
            "repository": {
                "owner": {"login": "test-owner"},
                "name": "test-repo",
            },
        }

        adapter._last_known_status["456"] = "open"

        events = []
        adapter.on("review.status_changed", events.append)

        await adapter.handle_webhook(payload)

        assert len(events) >= 1
        assert events[0].new_status == "closed"

    @pytest.mark.asyncio
    async def test_handle_webhook_validates_payload(self, adapter):
        """Test handle_webhook validates payload."""
        with pytest.raises(ValidationError):
            await adapter.handle_webhook(None)

        with pytest.raises(ValidationError):
            await adapter.handle_webhook([])


class TestStatusComputation:
    """Test review status computation logic."""

    def test_compute_review_status_merged_pr(self, adapter):
        """Test status computation for merged PR."""
        pr_node = {"state": "MERGED", "reviews": {"nodes": []}}

        status = adapter._compute_review_status(pr_node)
        assert status == "merged"

    def test_compute_review_status_closed_pr(self, adapter):
        """Test status computation for closed PR."""
        pr_node = {"state": "CLOSED", "reviews": {"nodes": []}}

        status = adapter._compute_review_status(pr_node)
        assert status == "closed"

    def test_compute_review_status_changes_requested(self, adapter):
        """Test status computation when changes requested."""
        pr_node = {
            "state": "OPEN",
            "reviews": {
                "nodes": [
                    {"state": "APPROVED"},
                    {"state": "CHANGES_REQUESTED"},
                ]
            },
        }

        status = adapter._compute_review_status(pr_node)
        assert status == "changes_requested"

    def test_compute_review_status_approved(self, adapter):
        """Test status computation when approved."""
        pr_node = {
            "state": "OPEN",
            "reviews": {
                "nodes": [
                    {"state": "APPROVED"},
                    {"state": "APPROVED"},
                ]
            },
        }

        status = adapter._compute_review_status(pr_node)
        assert status == "approved"

    def test_compute_review_status_open(self, adapter):
        """Test status computation for open PR with no reviews."""
        pr_node = {"state": "OPEN", "reviews": {"nodes": []}}

        status = adapter._compute_review_status(pr_node)
        assert status == "open"


class TestMapGitHubReviewState:
    """Test GitHub review state mapping."""

    def test_map_pending_to_open(self, adapter):
        """Test PENDING maps to open."""
        status = adapter._map_github_review_state("PENDING")
        assert status == "open"

    def test_map_approved_to_approved(self, adapter):
        """Test APPROVED maps to approved."""
        status = adapter._map_github_review_state("APPROVED")
        assert status == "approved"

    def test_map_changes_requested_to_changes_requested(self, adapter):
        """Test CHANGES_REQUESTED maps to changes_requested."""
        status = adapter._map_github_review_state("CHANGES_REQUESTED")
        assert status == "changes_requested"

    def test_map_dismissed_to_open(self, adapter):
        """Test DISMISSED maps to open."""
        status = adapter._map_github_review_state("DISMISSED")
        assert status == "open"

    def test_map_unknown_to_open(self, adapter):
        """Test unknown state maps to open."""
        status = adapter._map_github_review_state("UNKNOWN")
        assert status == "open"

    def test_map_none_to_open(self, adapter):
        """Test None maps to open."""
        status = adapter._map_github_review_state(None)
        assert status == "open"


class TestWorkItemLinkage:
    """Test work item ID linkage and caching."""

    def test_extract_work_item_id_from_branch(self, adapter):
        """Test extracting work item ID from branch name."""
        pr_data = {
            "headRefName": "feature/item-123",
            "body": "PR description",
        }

        work_item_id = adapter._extract_work_item_id(pr_data)
        assert work_item_id == "item-123"

    def test_extract_work_item_id_from_body(self, adapter):
        """Test extracting work item ID from PR body."""
        pr_data = {
            "headRefName": "feature/fix-bug",
            "body": "Fixes issue related to work item item-456",
        }

        work_item_id = adapter._extract_work_item_id(pr_data)
        assert work_item_id == "item-456"

    def test_extract_work_item_id_none_when_not_found(self, adapter):
        """Test None returned when work item ID not found."""
        pr_data = {
            "headRefName": "feature/fix-bug",
            "body": "Just a regular PR",
        }

        work_item_id = adapter._extract_work_item_id(pr_data)
        assert work_item_id is None


class TestPollingAdaptation:
    """Test adaptive polling interval adjustment."""

    def test_adapt_interval_reduces_on_activity(self, adapter):
        """Test interval reduces when changes detected."""
        adapter._polling_intervals["proj-1"] = 60.0

        adapter._adapt_polling_interval("proj-1", changes_detected=1)

        # Should reduce interval
        assert adapter._polling_intervals["proj-1"] < 60.0
        assert adapter._polling_intervals["proj-1"] >= 15.0

    def test_adapt_interval_increases_on_inactivity(self, adapter):
        """Test interval increases when no changes."""
        adapter._polling_intervals["proj-1"] = 60.0

        adapter._adapt_polling_interval("proj-1", changes_detected=0)

        # Should increase interval
        assert adapter._polling_intervals["proj-1"] > 60.0
        assert adapter._polling_intervals["proj-1"] <= 300.0

    def test_adapt_interval_respects_max(self, adapter):
        """Test interval respects maximum."""
        adapter._polling_intervals["proj-1"] = 300.0

        adapter._adapt_polling_interval("proj-1", changes_detected=0)

        # Should stay at max
        assert adapter._polling_intervals["proj-1"] <= 300.0

    def test_adapt_interval_respects_min(self, adapter):
        """Test interval respects minimum."""
        adapter._polling_intervals["proj-1"] = 15.0

        adapter._adapt_polling_interval("proj-1", changes_detected=5)

        # Should stay at min
        assert adapter._polling_intervals["proj-1"] >= 15.0
