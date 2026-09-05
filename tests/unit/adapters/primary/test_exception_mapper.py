"""
Tests for exception_mapper module

Ensures that domain, port, and input port exceptions are correctly
mapped to HTTP status codes and error responses.
"""

import pytest
from fastapi import HTTPException, status

from codetoreum.adapters.primary.exception_mapper import map_exception_to_http
from codetoreum.domain.exceptions import (
    AgentNotFoundError,
    ConfigNotFoundError,
    DomainError,
    ExecutionNotFoundError,
    InvalidStateError,
    PipelineNotFoundError,
    WorkspaceNotFoundError,
)
from codetoreum.domain.exceptions import (
    WorkItemNotFoundError as DomainWorkItemNotFoundError,
)
from codetoreum.ports.exceptions import (
    AuthenticationError,
    ConcurrencyConflictError,
    EmptyAgentResponseError,
    ExternalServiceError,
    PortError,
    RateLimitError,
    ResourceNotFoundError,
    TimeoutError,
)
from codetoreum.ports.exceptions import ValidationError as PortValidationError
from codetoreum.ports.input.exceptions import (
    AgentExecutionNotFoundError,
    ArtifactNotFoundError,
    CommandFileNotFoundError,
    CommandNotFoundError,
    PortException,
    ProjectNotFoundError,
    StageNotFoundError,
    SubAgentNotFoundError,
    VariableNotFoundError,
    WorkflowNotActiveError,
    WorkflowNotFoundError,
    WorkflowNotPausedError,
)
from codetoreum.ports.input.exceptions import (
    AgentNotFoundError as InputPortAgentNotFoundError,
)
from codetoreum.ports.input.exceptions import (
    PermissionError as InputPortPermissionError,
)
from codetoreum.ports.input.exceptions import (
    PipelineNotFoundError as InputPortPipelineNotFoundError,
)
from codetoreum.ports.input.exceptions import (
    ValidationError as InputPortValidationError,
)
from codetoreum.ports.input.exceptions import (
    WorkItemNotFoundError as InputPortWorkItemNotFoundError,
)


class TestDomainExceptionMapping:
    """Test mapping of domain layer exceptions"""

    def test_agent_not_found_maps_to_404(self):
        exc = AgentNotFoundError("agent-123")
        http_exc = map_exception_to_http(exc)

        assert isinstance(http_exc, HTTPException)
        assert http_exc.status_code == status.HTTP_404_NOT_FOUND
        assert "agent-123" in http_exc.detail

    def test_workspace_not_found_maps_to_404(self):
        exc = WorkspaceNotFoundError("ws-456")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND
        assert "ws-456" in http_exc.detail

    def test_config_not_found_maps_to_404(self):
        exc = ConfigNotFoundError("config-789")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND
        assert "config-789" in http_exc.detail

    def test_execution_not_found_maps_to_404(self):
        exc = ExecutionNotFoundError("exec-101")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND
        assert "exec-101" in http_exc.detail

    def test_pipeline_not_found_maps_to_404(self):
        exc = PipelineNotFoundError("pipeline-202")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND
        assert "pipeline-202" in http_exc.detail

    def test_work_item_not_found_maps_to_404(self):
        exc = DomainWorkItemNotFoundError("wi-303")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND
        assert "wi-303" in http_exc.detail

    def test_invalid_state_error_maps_to_400(self):
        exc = InvalidStateError("Cannot transition from stopped to paused")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cannot transition" in http_exc.detail


class TestInputPortExceptionMapping:
    """Test mapping of input port layer exceptions"""

    def test_project_not_found_maps_to_404(self):
        exc = ProjectNotFoundError("Project not found")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND
        assert "Project not found" in http_exc.detail

    def test_workflow_not_found_maps_to_404(self):
        exc = WorkflowNotFoundError("Workflow not found")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND

    def test_stage_not_found_maps_to_404(self):
        exc = StageNotFoundError("Stage not found")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND

    def test_agent_execution_not_found_maps_to_404(self):
        exc = AgentExecutionNotFoundError("Execution not found")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND

    def test_artifact_not_found_maps_to_404(self):
        exc = ArtifactNotFoundError("Artifact not found")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND

    def test_command_not_found_maps_to_404(self):
        exc = CommandNotFoundError("Command not found")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND

    def test_validation_error_maps_to_400(self):
        exc = InputPortValidationError("Invalid input data")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid input data" in http_exc.detail

    def test_workflow_not_active_maps_to_409(self):
        exc = WorkflowNotActiveError("Workflow must be active")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_409_CONFLICT
        assert "Workflow must be active" in http_exc.detail

    def test_workflow_not_paused_maps_to_409(self):
        exc = WorkflowNotPausedError("Workflow must be paused")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_409_CONFLICT
        assert "Workflow must be paused" in http_exc.detail

    def test_permission_error_maps_to_403(self):
        exc = InputPortPermissionError("Access denied")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_403_FORBIDDEN
        assert "Access denied" in http_exc.detail


class TestPortExceptionMapping:
    """Test mapping of port layer (external service) exceptions"""

    def test_resource_not_found_maps_to_404(self):
        exc = ResourceNotFoundError("WorkItem", "wi-123")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND
        assert "wi-123" in http_exc.detail

    def test_validation_error_maps_to_400(self):
        exc = PortValidationError("Invalid data format")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid data format" in http_exc.detail

    def test_empty_agent_response_maps_to_502(self):
        exc = EmptyAgentResponseError("issue-42")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_502_BAD_GATEWAY
        assert "issue-42" in http_exc.detail
        assert "empty" in http_exc.detail.lower()

    def test_authentication_error_maps_to_401(self):
        exc = AuthenticationError("Invalid token")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid token" in http_exc.detail
        assert http_exc.headers is not None
        assert "WWW-Authenticate" in http_exc.headers
        assert http_exc.headers["WWW-Authenticate"] == "Bearer"

    def test_concurrency_conflict_maps_to_409(self):
        exc = ConcurrencyConflictError("Version mismatch")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_409_CONFLICT
        assert "Version mismatch" in http_exc.detail

    def test_rate_limit_error_maps_to_429(self):
        exc = RateLimitError(retry_after=60)
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert http_exc.headers is not None
        assert "Retry-After" in http_exc.headers
        assert http_exc.headers["Retry-After"] == "60"

    def test_rate_limit_without_retry_after(self):
        exc = RateLimitError(retry_after=None)
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert http_exc.headers is None

    def test_timeout_error_maps_to_504(self):
        exc = TimeoutError("Request timed out")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_504_GATEWAY_TIMEOUT
        assert "Request timed out" in http_exc.detail

    def test_external_service_error_maps_to_502(self):
        exc = ExternalServiceError(service="GitHub", message="API unavailable")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_502_BAD_GATEWAY
        assert "GitHub" in http_exc.detail

    def test_generic_port_error_maps_to_502(self):
        exc = PortError("Something went wrong with external service")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_502_BAD_GATEWAY


class TestGenericExceptionMapping:
    """Test mapping of generic and unknown exceptions"""

    def test_generic_port_exception_maps_to_500(self):
        exc = PortException("Command failed")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_generic_domain_error_maps_to_500(self):
        exc = DomainError("Business rule violation")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Business rule violation" in http_exc.detail

    def test_unknown_exception_maps_to_500(self):
        exc = RuntimeError("Unexpected error")
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert http_exc.detail == "An internal error occurred"

    def test_empty_exception_message_uses_default(self):
        exc = ValueError("")
        http_exc = map_exception_to_http(exc, default_detail="Something went wrong")

        assert http_exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert http_exc.detail == "Something went wrong"


class TestExceptionMessageHandling:
    """Test proper handling of exception messages"""

    def test_exception_message_preserved(self):
        exc = ProjectNotFoundError("Project proj-123 not found")
        http_exc = map_exception_to_http(exc)

        assert "proj-123" in http_exc.detail

    def test_empty_message_uses_default_detail(self):
        # Create a custom exception with no message
        class EmptyException(DomainError):
            def __init__(self):
                super().__init__("")

        exc = EmptyException()
        http_exc = map_exception_to_http(exc, default_detail="Default message")

        assert http_exc.detail == "Default message"

    def test_none_message_uses_default_detail(self):
        exc = DomainError("")
        http_exc = map_exception_to_http(exc, default_detail="Fallback message")

        assert http_exc.detail == "Fallback message"


class TestAllNotFoundExceptions:
    """Comprehensive test for all NotFound exception types"""

    @pytest.mark.parametrize(
        "exception_class,exception_args",
        [
            (AgentNotFoundError, ("agent-1",)),
            (WorkspaceNotFoundError, ("ws-1",)),
            (ConfigNotFoundError, ("config-1",)),
            (ExecutionNotFoundError, ("exec-1",)),
            (PipelineNotFoundError, ("pipeline-1",)),
            (DomainWorkItemNotFoundError, ("wi-1",)),
            (InputPortAgentNotFoundError, ("Agent not found",)),
            (AgentExecutionNotFoundError, ("Execution not found",)),
            (ArtifactNotFoundError, ("Artifact not found",)),
            (CommandFileNotFoundError, ("Command file not found",)),
            (CommandNotFoundError, ("Command not found",)),
            (InputPortPipelineNotFoundError, ("Pipeline not found",)),
            (ProjectNotFoundError, ("Project not found",)),
            (StageNotFoundError, ("Stage not found",)),
            (SubAgentNotFoundError, ("SubAgent not found",)),
            (VariableNotFoundError, ("Variable not found",)),
            (WorkflowNotFoundError, ("Workflow not found",)),
            (InputPortWorkItemNotFoundError, ("WorkItem not found",)),
            (ResourceNotFoundError, ("Resource", "res-1")),
        ],
    )
    def test_all_not_found_exceptions_map_to_404(self, exception_class, exception_args):
        """Test that all NotFound exceptions map to 404"""
        exc = exception_class(*exception_args)
        http_exc = map_exception_to_http(exc)

        assert http_exc.status_code == status.HTTP_404_NOT_FOUND
        assert isinstance(http_exc, HTTPException)
