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
from unittest.mock import MagicMock, patch

import pytest

from codetoreum.adapters.secondary.github_ci_pipeline_adapter import (
    GitHubCIPipelineAdapter,
)
from codetoreum.adapters.secondary.github_ticket_adapter import (
    GitHubConfig,
    GitHubTicketAdapter,
)
from codetoreum.domain.events.ci_pipeline_events import (
    CIPipelineStatusCheckedEvent,
    CIRunCompletedEvent,
    CIRunStartedEvent,
)
from codetoreum.ports.exceptions import (
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.ci_pipeline_service import (
    CICheckResult,
    CICheckStatus,
    CIPipelineStatus,
)
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
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {"repository": {"pullRequest": None}}

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
                    "commits": {"nodes": []},  # No commits yet
                }
            }
        }

        status = await adapter.get_pr_ci_status("123", "proj-1")

        assert status.total_checks == 0
        assert status.status == CICheckStatus.PENDING

    async def test_event_construction_failure_does_not_discard_status(self, adapter, mock_graphql_client, caplog):
        """Test that event construction failure doesn't prevent returning CI status.

        This is the core requirement: even if event construction fails, the CI status
        must still be returned successfully. Event failures are logged but isolated
        from the primary operation.
        """
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

        # Force event construction to fail by patching CIPipelineStatusCheckedEvent
        with patch(
            "codetoreum.adapters.secondary.github_ci_pipeline_adapter.CIPipelineStatusCheckedEvent",
            side_effect=ValueError("Simulated event construction failure"),
        ):
            # Should NOT raise - status must be returned despite event failure
            status = await adapter.get_pr_ci_status("123", "proj-1")

        # Verify CI status was returned successfully
        assert status.pr_id == "123"
        assert status.status == CICheckStatus.PASSED
        assert status.total_checks == 1

        # Verify error was logged with proper error ID
        assert any(
            "ERR_EVENT_PUBLICATION_ERROR" in record.getMessage()
            or record.__dict__.get("error_id") == "ERR_EVENT_PUBLICATION_ERROR"
            for record in caplog.records
        )


class TestRunCIChecks:
    """Test run_ci_checks method and conversion utilities."""

    async def test_run_ci_checks_happy_path(self, adapter, mock_graphql_client, tmp_path):
        """Test happy path: branch with open PR → CI status → CIRunResult."""
        import subprocess

        # Initialize a real git repo
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True, capture_output=True)

        # Create initial commit on main so we can create a feature branch
        (repo_dir / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)

        # Create and checkout a feature branch
        subprocess.run(["git", "checkout", "-b", "feature-branch"], cwd=repo_dir, check=True, capture_output=True)

        # Mock GraphQL responses
        # First query: resolve PR by branch name
        mock_graphql_client.responses["GetPullRequestByBranch"] = {
            "repository": {
                "pullRequests": {
                    "nodes": [
                        {
                            "number": 456,
                        }
                    ]
                }
            }
        }

        # Second query: get PR CI status
        mock_graphql_client.responses["GetPullRequestCheckRuns"] = {
            "repository": {
                "pullRequest": {
                    "number": 456,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "def456",
                                    "checkSuites": {
                                        "nodes": [
                                            {
                                                "status": "COMPLETED",
                                                "conclusion": "SUCCESS",
                                                "checkRuns": {
                                                    "nodes": [
                                                        {
                                                            "name": "unit-tests",
                                                            "status": "COMPLETED",
                                                            "conclusion": "SUCCESS",
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

        async def mock_execute(query: str, variables: dict | None = None) -> dict:
            """Route to appropriate response."""
            if "GetPullRequestByBranch" in query:
                return mock_graphql_client.responses.get("GetPullRequestByBranch", {})
            if "GetPullRequestCheckRuns" in query:
                return mock_graphql_client.responses.get("GetPullRequestCheckRuns", {})
            return {}

        mock_graphql_client.execute = mock_execute

        result = await adapter.run_ci_checks("proj-1", str(repo_dir), timeout_seconds=600)

        assert result.passed is True
        assert result.failed == 0
        assert len(result.check_results) == 1
        assert result.check_results[0].name == "unit-tests"
        assert result.check_results[0].status == CICheckStatus.PASSED

    async def test_run_ci_checks_no_pr_for_branch(self, adapter, mock_graphql_client, tmp_path):
        """Test ResourceNotFoundError when no open PR exists for branch."""
        import subprocess

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True, capture_output=True)

        # Create initial commit
        (repo_dir / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)

        subprocess.run(["git", "checkout", "-b", "orphan-branch"], cwd=repo_dir, check=True, capture_output=True)

        # Mock response: no PR found
        async def mock_execute(query: str, variables: dict | None = None) -> dict:
            return {
                "repository": {
                    "pullRequests": {
                        "nodes": []  # No PRs found
                    }
                }
            }

        mock_graphql_client.execute = mock_execute

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.run_ci_checks("proj-1", str(repo_dir))

        assert exc_info.value.resource_type == "PullRequest"

    async def test_run_ci_checks_not_a_git_repo(self, adapter, tmp_path):
        """Test ValidationError when working_directory is not a git repo."""
        non_repo_dir = tmp_path / "not-repo"
        non_repo_dir.mkdir()

        with pytest.raises(ValidationError) as exc_info:
            await adapter.run_ci_checks("proj-1", str(non_repo_dir))

        assert "not a git repository" in str(exc_info.value)

    async def test_run_ci_checks_directory_not_exist(self, adapter):
        """Test ValidationError when working_directory doesn't exist."""
        with pytest.raises(ValidationError) as exc_info:
            await adapter.run_ci_checks("proj-1", "/nonexistent/path/to/repo")

        assert "does not exist" in str(exc_info.value)

    async def test_run_ci_checks_propagates_ci_status_exception(self, adapter, mock_graphql_client, tmp_path):
        """Test that exceptions from get_pr_ci_status propagate unchanged."""
        import subprocess

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True, capture_output=True)

        # Create initial commit
        (repo_dir / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)

        subprocess.run(["git", "checkout", "-b", "test-branch"], cwd=repo_dir, check=True, capture_output=True)

        # First call succeeds (resolve PR)
        async def mock_execute(query: str, variables: dict | None = None) -> dict:
            if "GetPullRequestByBranch" in query:
                return {
                    "repository": {
                        "pullRequests": {
                            "nodes": [{"number": 789}]
                        }
                    }
                }
            # Second call raises
            raise ExternalServiceError(service="GitHub", message="API unavailable")

        mock_graphql_client.execute = mock_execute

        with pytest.raises(ExternalServiceError) as exc_info:
            await adapter.run_ci_checks("proj-1", str(repo_dir))

        assert exc_info.value.service == "GitHub"

    async def test_run_ci_checks_emits_started_and_completed_events(self, adapter, mock_graphql_client, tmp_path):
        """Test that run_ci_checks emits both CIRunStartedEvent and CIRunCompletedEvent."""
        import subprocess

        # Initialize a real git repo
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True, capture_output=True)

        # Create initial commit on main so we can create a feature branch
        (repo_dir / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)

        # Create and checkout a feature branch
        subprocess.run(["git", "checkout", "-b", "feature-branch"], cwd=repo_dir, check=True, capture_output=True)

        # Mock GraphQL responses
        async def mock_execute(query: str, variables: dict | None = None) -> dict:
            """Route to appropriate response."""
            if "GetPullRequestByBranch" in query:
                return {
                    "repository": {
                        "pullRequests": {
                            "nodes": [
                                {
                                    "number": 456,
                                }
                            ]
                        }
                    }
                }
            if "GetPullRequestCheckRuns" in query:
                return {
                    "repository": {
                        "pullRequest": {
                            "number": 456,
                            "commits": {
                                "nodes": [
                                    {
                                        "commit": {
                                            "oid": "def456",
                                            "checkSuites": {
                                                "nodes": [
                                                    {
                                                        "status": "COMPLETED",
                                                        "conclusion": "SUCCESS",
                                                        "checkRuns": {
                                                            "nodes": [
                                                                {
                                                                    "name": "unit-tests",
                                                                    "status": "COMPLETED",
                                                                    "conclusion": "SUCCESS",
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
            return {}

        mock_graphql_client.execute = mock_execute

        # Capture events
        started_event = None
        completed_event = None

        def capture_started(event):
            nonlocal started_event
            started_event = event

        def capture_completed(event):
            nonlocal completed_event
            completed_event = event

        adapter.on("ci.run_started", capture_started)
        adapter.on("ci.run_completed", capture_completed)

        # Execute
        result = await adapter.run_ci_checks("proj-1", str(repo_dir), timeout_seconds=600)

        # Verify both events were emitted
        assert started_event is not None
        assert isinstance(started_event, CIRunStartedEvent)
        assert started_event.type == "ci.run_started"
        assert started_event.project_id == "proj-1"
        assert started_event.working_directory == str(repo_dir)
        assert started_event.timeout_seconds == 600

        assert completed_event is not None
        assert isinstance(completed_event, CIRunCompletedEvent)
        assert completed_event.type == "ci.run_completed"
        assert completed_event.project_id == "proj-1"
        assert completed_event.passed_count == 1
        assert completed_event.failure_count == 0

        # Verify same workflow_run_id in both events
        assert started_event.workflow_run_id == completed_event.workflow_run_id

        # Verify result is correct
        assert result.passed is True
        assert result.failed == 0


class TestConvertCIStatusToRunResult:
    """Test CIPipelineStatus to CIRunResult conversion."""

    def test_convert_all_passed(self, adapter):
        """Test conversion when all checks passed."""
        ci_status = CIPipelineStatus(
            pr_id="123",
            status=CICheckStatus.PASSED,
            check_results=(
                CICheckResult(name="test-1", status=CICheckStatus.PASSED, conclusion="success"),
                CICheckResult(name="test-2", status=CICheckStatus.PASSED, conclusion="success"),
            ),
            total_checks=2,
            passed=2,
            failed=0,
            pending=0,
            pipeline_url="https://github.com/runs/123",
        )

        result = adapter._convert_ci_status_to_run_result(ci_status)

        assert result.passed is True
        assert result.failed == 0
        assert len(result.failures) == 0
        assert len(result.check_results) == 2
        assert result.warnings == ()
        assert "Pipeline Status: passed" in result.output
        assert "Total checks: 2" in result.output
        assert "Passed: 2" in result.output

    def test_convert_mixed_pass_fail(self, adapter):
        """Test conversion with mixed pass/fail results."""
        ci_status = CIPipelineStatus(
            pr_id="123",
            status=CICheckStatus.FAILED,
            check_results=(
                CICheckResult(name="test-1", status=CICheckStatus.PASSED, conclusion="success"),
                CICheckResult(name="test-2", status=CICheckStatus.FAILED, conclusion="failure"),
                CICheckResult(name="test-3", status=CICheckStatus.FAILED, conclusion="timeout"),
            ),
            total_checks=3,
            passed=1,
            failed=2,
            pending=0,
            pipeline_url="",
        )

        result = adapter._convert_ci_status_to_run_result(ci_status)

        assert result.passed is False
        assert result.failed == 2
        assert len(result.failures) == 2
        assert "test-2: failure" in result.failures
        assert "test-3: timeout" in result.failures
        assert "Failed: 2" in result.output

    def test_convert_pending_checks(self, adapter):
        """Test conversion with pending checks treats as not passed."""
        ci_status = CIPipelineStatus(
            pr_id="123",
            status=CICheckStatus.PENDING,
            check_results=(
                CICheckResult(name="test-1", status=CICheckStatus.PASSED, conclusion="success"),
                CICheckResult(name="test-2", status=CICheckStatus.PENDING, conclusion=None),
            ),
            total_checks=2,
            passed=1,
            failed=0,
            pending=1,
            pipeline_url="",
        )

        result = adapter._convert_ci_status_to_run_result(ci_status)

        assert result.passed is False
        # Pending count added to failed count to satisfy contract (passed=False requires failed > 0)
        assert result.failed == 1
        # Pending checks are included in failures list to represent "not yet passed"
        assert len(result.failures) == 1
        assert "test-2" in result.failures[0]
        assert "pending/in-progress" in result.failures[0]
        assert "Pending/Running: 1" in result.output

    def test_convert_empty_checks(self, adapter):
        """Test conversion with no checks (skipped status) - treated as passed since nothing to check."""
        ci_status = CIPipelineStatus(
            pr_id="123",
            status=CICheckStatus.SKIPPED,
            check_results=(),
            total_checks=0,
            passed=0,
            failed=0,
            pending=0,
            pipeline_url="",
        )

        result = adapter._convert_ci_status_to_run_result(ci_status)

        # With no checks at all, it's not failed (nothing failed), so passed=True
        # This matches the "no failing conditions" semantic
        assert result.passed is True
        assert result.failed == 0
        assert len(result.check_results) == 0
        assert len(result.failures) == 0

    def test_convert_running_checks(self, adapter):
        """Test conversion with running checks treats as not passed."""
        ci_status = CIPipelineStatus(
            pr_id="123",
            status=CICheckStatus.PENDING,
            check_results=(CICheckResult(name="test-1", status=CICheckStatus.RUNNING, conclusion=None),),
            total_checks=1,
            passed=0,
            failed=0,
            pending=1,
            pipeline_url="https://github.com/runs/456",
        )

        result = adapter._convert_ci_status_to_run_result(ci_status)

        assert result.passed is False
        # Running checks are converted to FAILED for contract compliance (passed=False requires failed > 0)
        assert result.failed == 1
        assert len(result.failures) == 1
        assert "test-1" in result.failures[0]
        assert "pending/in-progress" in result.failures[0]
        assert "Pipeline URL: https://github.com/runs/456" in result.output

    def test_convert_failure_without_conclusion(self, adapter):
        """Test conversion handles failed checks without conclusion gracefully."""
        ci_status = CIPipelineStatus(
            pr_id="123",
            status=CICheckStatus.FAILED,
            check_results=(CICheckResult(name="mysterious-check", status=CICheckStatus.FAILED, conclusion=None),),
            total_checks=1,
            passed=0,
            failed=1,
            pending=0,
            pipeline_url="",
        )

        result = adapter._convert_ci_status_to_run_result(ci_status)

        assert result.passed is False
        assert result.failed == 1
        assert len(result.failures) == 1
        assert "mysterious-check" in result.failures[0]
