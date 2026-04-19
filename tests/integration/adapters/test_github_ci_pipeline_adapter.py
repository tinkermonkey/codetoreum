"""Integration tests for GitHubCIPipelineAdapter.

Tests verify:
- PR CI status queries via GraphQL
- Check run aggregation and status mapping
- Event emission on status queries
- Error handling (PR not found, invalid input, API errors)
- Monitoring lifecycle management
- Proper encapsulation of ticket adapter configuration
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from codetoreum.adapters.secondary.github_ci_pipeline_adapter import (
    GitHubCIPipelineAdapter,
)
from codetoreum.adapters.secondary.github_ticket_adapter import (
    GitHubConfig,
    GitHubTicketAdapter,
)
from codetoreum.domain.events.ci_pipeline_events import CIPipelineStatusCheckedEvent
from codetoreum.ports.exceptions import (
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.ci_pipeline_service import CICheckStatus
from codetoreum.ports.output.monitoring import MonitoringConfig, MonitoringState


class MockGraphQLClient:
    """Mock GraphQL client for testing without real GitHub API calls."""

    def __init__(self):
        self.queries: list[tuple] = []
        self.responses: dict[str, Any] = {}
        self.call_count: int = 0

    async def execute(self, query: str, variables: dict | None = None) -> dict[str, Any]:
        """Record query and return mock response."""
        self.queries.append((query, variables))
        self.call_count += 1

        # Return mock response based on query name
        if "GetPullRequestCheckRuns" in query:
            result: dict[str, Any] = self.responses.get(
                "GetPullRequestCheckRuns",
                {
                    "repository": {
                        "pullRequest": {
                            "number": 123,
                            "commits": {
                                "nodes": [
                                    {
                                        "commit": {
                                            "oid": "abc123",
                                            "checkSuites": {"nodes": []},
                                        }
                                    }
                                ]
                            },
                        }
                    }
                },
            )
            return result

        return {}

    async def close(self) -> None:
        """Close client."""


@pytest.fixture
def github_config():
    """Provide GitHub configuration."""
    return GitHubConfig(
        token="test-token",
        organization="test-owner",
        repository="test-repo",
    )


@pytest.fixture
def ticket_adapter(github_config):
    """Provide real GitHubTicketAdapter instance."""
    return GitHubTicketAdapter(github_config)


@pytest.fixture
def mock_graphql_client():
    """Provide mock GraphQL client."""
    return MockGraphQLClient()


@pytest.fixture
def adapter(ticket_adapter, mock_graphql_client):
    """Provide GitHubCIPipelineAdapter instance."""
    return GitHubCIPipelineAdapter(
        ticket_adapter=ticket_adapter,
        graphql_client=mock_graphql_client,
    )


class TestGetOwnerRepo:
    """Test owner/repo retrieval without violating encapsulation."""

    async def test_get_owner_repo_via_public_method(self, adapter):
        """Test _get_owner_repo uses public method on ticket adapter."""
        owner, repo = await adapter._get_owner_repo()

        assert owner == "test-owner"
        assert repo == "test-repo"

    async def test_get_owner_repo_raises_on_invalid_adapter(self):
        """Test _get_owner_repo raises descriptive error on invalid adapter."""
        bad_adapter = MagicMock()
        bad_adapter.get_owner_repo.side_effect = ValueError("Missing owner/repo config")
        graphql = MockGraphQLClient()

        adapter = GitHubCIPipelineAdapter(
            ticket_adapter=bad_adapter,
            graphql_client=graphql,
        )

        with pytest.raises(ExternalServiceError) as exc_info:
            await adapter._get_owner_repo()

        error = exc_info.value
        assert error.service == "GitHub"
        assert "Missing owner/repo config" in str(error)


class TestEventEmitter:
    """Test IEventEmitter implementation."""

    def test_on_registers_handler(self, adapter):
        """Test registering event handler."""
        handler = MagicMock()
        adapter.on("ci.pipeline_status_checked", handler)

        assert "ci.pipeline_status_checked" in adapter._event_handlers
        assert handler in adapter._event_handlers["ci.pipeline_status_checked"]

    def test_off_unregisters_handler(self, adapter):
        """Test unregistering event handler."""
        handler = MagicMock()
        adapter.on("ci.pipeline_status_checked", handler)
        adapter.off("ci.pipeline_status_checked", handler)

        assert handler not in adapter._event_handlers.get("ci.pipeline_status_checked", [])

    def test_emit_calls_handlers(self, adapter):
        """Test emitting event calls all handlers."""
        handler1 = MagicMock()
        handler2 = MagicMock()

        adapter.on("ci.pipeline_status_checked", handler1)
        adapter.on("ci.pipeline_status_checked", handler2)

        event = CIPipelineStatusCheckedEvent(
            type="ci.pipeline_status_checked",
            timestamp="2024-01-01T10:00:00Z",
            source="github",
            pr_id="123",
            project_id="proj-1",
            status="passed",
            check_count=3,
            passed_count=3,
            failed_count=0,
            pending_count=0,
        )

        adapter.emit(event)

        handler1.assert_called_once_with(event)
        handler2.assert_called_once_with(event)

    def test_emit_handles_handler_errors(self, adapter, caplog):
        """Test emit continues on handler error."""
        handler1 = MagicMock(side_effect=Exception("Handler error"))
        handler2 = MagicMock()

        adapter.on("ci.pipeline_status_checked", handler1)
        adapter.on("ci.pipeline_status_checked", handler2)

        event = CIPipelineStatusCheckedEvent(
            type="ci.pipeline_status_checked",
            timestamp="2024-01-01T10:00:00Z",
            source="github",
            pr_id="123",
            project_id="proj-1",
            status="passed",
            check_count=3,
            passed_count=3,
            failed_count=0,
            pending_count=0,
        )

        # Should not raise
        adapter.emit(event)

        handler1.assert_called_once()
        handler2.assert_called_once()


class TestMonitoring:
    """Test IMonitoredService implementation."""

    async def test_start_monitoring(self, adapter):
        """Test starting CI status monitoring."""
        config = MonitoringConfig(project_id="proj-1")
        await adapter.start_monitoring("proj-1", config)

        status = await adapter.get_monitoring_status("proj-1")
        assert status.state == MonitoringState.ACTIVE
        assert status.project_id == "proj-1"

    async def test_stop_monitoring(self, adapter):
        """Test stopping CI status monitoring."""
        config = MonitoringConfig(project_id="proj-1")
        await adapter.start_monitoring("proj-1", config)
        await adapter.stop_monitoring("proj-1")

        status = await adapter.get_monitoring_status("proj-1")
        assert status.state == MonitoringState.STOPPED
        assert status.project_id == "proj-1"

    async def test_get_monitoring_status_before_start(self, adapter):
        """Test getting monitoring status for unstarted project."""
        status = await adapter.get_monitoring_status("proj-1")

        assert status.state == MonitoringState.STOPPED
        assert status.project_id == "proj-1"


class TestGetPRCIStatus:
    """Test get_pr_ci_status method."""

    async def test_valid_pr_with_no_checks(self, adapter, mock_graphql_client):
        """Test PR query returns pipeline status with no checks."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "checkSuites": {"nodes": []},
                                }
                            }
                        ]
                    },
                }
            }
        }

        status = await adapter.get_pr_ci_status("123", "proj-1")

        assert status.pr_id == "123"
        assert status.total_checks == 0
        assert status.status == CICheckStatus.SKIPPED
        assert len(mock_graphql_client.queries) == 1

    async def test_valid_pr_with_passing_checks(self, adapter, mock_graphql_client):
        """Test PR with all checks passing."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "COMPLETED",
                                                "conclusion": "SUCCESS",
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "test-suite",
                                                            "status": "COMPLETED",
                                                            "conclusion": "SUCCESS",
                                                            "detailsUrl": "https://github.com/test",
                                                        },
                                                        {
                                                            "name": "linting",
                                                            "status": "COMPLETED",
                                                            "conclusion": "SUCCESS",
                                                            "detailsUrl": "https://github.com/lint",
                                                        },
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }

        status = await adapter.get_pr_ci_status("123", "proj-1")

        assert status.pr_id == "123"
        assert status.total_checks == 2
        assert status.passed == 2
        assert status.failed == 0
        assert status.status == CICheckStatus.PASSED
        assert len(status.check_results) == 2

    async def test_valid_pr_with_failing_checks(self, adapter, mock_graphql_client):
        """Test PR with some checks failing."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "COMPLETED",
                                                "conclusion": "FAILURE",
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "unit-tests",
                                                            "status": "COMPLETED",
                                                            "conclusion": "SUCCESS",
                                                            "detailsUrl": "https://github.com/unit",
                                                        },
                                                        {
                                                            "name": "integration-tests",
                                                            "status": "COMPLETED",
                                                            "conclusion": "FAILURE",
                                                            "detailsUrl": "https://github.com/integration",
                                                        },
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }

        status = await adapter.get_pr_ci_status("123", "proj-1")

        assert status.pr_id == "123"
        assert status.total_checks == 2
        assert status.passed == 1
        assert status.failed == 1
        assert status.status == CICheckStatus.FAILED

    async def test_valid_pr_with_pending_checks(self, adapter, mock_graphql_client):
        """Test PR with some checks still pending."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "IN_PROGRESS",
                                                "conclusion": None,
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "slow-test",
                                                            "status": "QUEUED",
                                                            "conclusion": None,
                                                            "detailsUrl": None,
                                                        },
                                                        {
                                                            "name": "fast-test",
                                                            "status": "COMPLETED",
                                                            "conclusion": "SUCCESS",
                                                            "detailsUrl": "https://github.com/fast",
                                                        },
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }

        status = await adapter.get_pr_ci_status("123", "proj-1")

        assert status.pr_id == "123"
        assert status.passed == 1
        assert status.pending == 1
        assert status.status == CICheckStatus.PENDING

    async def test_valid_pr_with_running_checks(self, adapter, mock_graphql_client):
        """Test PR with checks currently running (overall status maps to PENDING per design)."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "IN_PROGRESS",
                                                "conclusion": None,
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "tests",
                                                            "status": "IN_PROGRESS",
                                                            "conclusion": None,
                                                            "detailsUrl": "https://github.com/tests",
                                                        }
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }

        status = await adapter.get_pr_ci_status("123", "proj-1")

        assert status.pr_id == "123"
        # Overall status maps running checks to PENDING (per current design)
        assert status.status == CICheckStatus.PENDING
        # But individual check is RUNNING
        assert status.check_results[0].status == CICheckStatus.RUNNING

    async def test_emits_event_on_status_query(self, adapter, mock_graphql_client):
        """Test that status query emits a domain event."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "COMPLETED",
                                                "conclusion": "SUCCESS",
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "test",
                                                            "status": "COMPLETED",
                                                            "conclusion": "SUCCESS",
                                                            "detailsUrl": "https://github.com",
                                                        }
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }

        event_emitted = None

        def capture_event(event):
            nonlocal event_emitted
            event_emitted = event

        adapter.on("ci.pipeline_status_checked", capture_event)
        await adapter.get_pr_ci_status("123", "proj-1")

        assert event_emitted is not None
        assert isinstance(event_emitted, CIPipelineStatusCheckedEvent)
        assert event_emitted.pr_id == "123"
        assert event_emitted.status == "passed"
        assert event_emitted.check_count == 1

    async def test_validation_error_on_empty_pr_id(self, adapter):
        """Test validation error on empty pr_id."""
        with pytest.raises(ValidationError):
            await adapter.get_pr_ci_status("", "proj-1")

    async def test_validation_error_on_non_numeric_pr_id(self, adapter):
        """Test validation error on non-numeric pr_id."""
        with pytest.raises(ValidationError) as exc_info:
            await adapter.get_pr_ci_status("not-a-number", "proj-1")

        assert "must be numeric" in str(exc_info.value)

    async def test_validation_error_on_empty_project_id(self, adapter):
        """Test validation error on empty project_id."""
        with pytest.raises(ValidationError):
            await adapter.get_pr_ci_status("123", "")

    async def test_resource_not_found_error(self, adapter, mock_graphql_client):
        """Test ResourceNotFoundError when PR doesn't exist."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": None
            }
        }

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.get_pr_ci_status("999", "proj-1")

        assert exc_info.value.resource_id == "999"
        assert exc_info.value.resource_type == "PullRequest"

    async def test_external_service_error_on_graphql_failure(self, adapter, mock_graphql_client):
        """Test ExternalServiceError on GraphQL API failure."""
        async def failing_execute(*args, **kwargs):
            raise RuntimeError("GraphQL API unavailable")

        mock_graphql_client.execute = failing_execute

        with pytest.raises(ExternalServiceError) as exc_info:
            await adapter.get_pr_ci_status("123", "proj-1")

        assert exc_info.value.service == "GitHub"

    async def test_external_service_error_on_invalid_response_format(self, adapter, mock_graphql_client):
        """Test ExternalServiceError on invalid GraphQL response format (non-dict checkRuns)."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "COMPLETED",
                                                "conclusion": "SUCCESS",
                                                "checkRuns": "invalid_not_dict",  # This will cause AttributeError
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }

        with pytest.raises(ExternalServiceError) as exc_info:
            await adapter.get_pr_ci_status("123", "proj-1")

        assert exc_info.value.service == "GitHub"
        # Error message should contain the format error description from _parse_check_runs
        assert "Invalid check runs response format" in str(exc_info.value)

    async def test_check_status_mapping_neutral(self, adapter, mock_graphql_client):
        """Test status mapping for neutral conclusion (treated as passed)."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "COMPLETED",
                                                "conclusion": "NEUTRAL",
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "optional-check",
                                                            "status": "COMPLETED",
                                                            "conclusion": "NEUTRAL",
                                                            "detailsUrl": "https://github.com",
                                                        }
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }

        status = await adapter.get_pr_ci_status("123", "proj-1")

        assert status.status == CICheckStatus.PASSED
        assert status.passed == 1

    async def test_check_status_mapping_skipped(self, adapter, mock_graphql_client):
        """Test status mapping for skipped checks."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "COMPLETED",
                                                "conclusion": "SKIPPED",
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "conditional-check",
                                                            "status": "COMPLETED",
                                                            "conclusion": "SKIPPED",
                                                            "detailsUrl": None,
                                                        }
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }

        status = await adapter.get_pr_ci_status("123", "proj-1")

        assert status.check_results[0].status == CICheckStatus.SKIPPED
        assert status.status == CICheckStatus.SKIPPED

    async def test_check_status_mapping_timed_out(self, adapter, mock_graphql_client):
        """Test status mapping for timed out checks."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "COMPLETED",
                                                "conclusion": "TIMED_OUT",
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "slow-check",
                                                            "status": "COMPLETED",
                                                            "conclusion": "TIMED_OUT",
                                                            "detailsUrl": "https://github.com",
                                                        }
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }

        status = await adapter.get_pr_ci_status("123", "proj-1")

        assert status.check_results[0].status == CICheckStatus.FAILED
        assert status.status == CICheckStatus.FAILED

    async def test_multiple_check_suites(self, adapter, mock_graphql_client):
        """Test PR with multiple check suites."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc123",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "COMPLETED",
                                                "conclusion": "SUCCESS",
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "build",
                                                            "status": "COMPLETED",
                                                            "conclusion": "SUCCESS",
                                                            "detailsUrl": "https://github.com/build",
                                                        }
                                                    ]
                                                },
                                            },
                                            {
                                                "status": "COMPLETED",
                                                "conclusion": "SUCCESS",
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "test",
                                                            "status": "COMPLETED",
                                                            "conclusion": "SUCCESS",
                                                            "detailsUrl": "https://github.com/test",
                                                        }
                                                    ]
                                                },
                                            },
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }

        status = await adapter.get_pr_ci_status("123", "proj-1")

        assert status.total_checks == 2
        assert status.passed == 2
        assert status.status == CICheckStatus.PASSED

    async def test_no_commits_returns_pending(self, adapter, mock_graphql_client):
        """Test PR with no commits returns pending status."""
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 123,
                    "commits": {
                        "nodes": []  # No commits yet
                    },
                }
            }
        }

        status = await adapter.get_pr_ci_status("123", "proj-1")

        assert status.total_checks == 0
        assert status.status == CICheckStatus.PENDING
