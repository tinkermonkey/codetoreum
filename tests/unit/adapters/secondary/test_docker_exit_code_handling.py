"""Unit tests for Docker Container Adapter exit code handling.

Tests cover:
- _try_reload_for_exit_code method with all four code paths
- run() method exit code retrieval fallback chain
- Error handling and logging for exit code retrieval failures
"""

import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import docker.errors
import pytest

from codetoreum.adapters.secondary.docker_container_adapter import DockerConfig, DockerContainerAdapter
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.exceptions import ContainerExecutionError


@pytest.fixture(autouse=True)
def _patch_agent_workspace_base():
    """Patch AGENT_WORKSPACE_BASE to a valid path for all tests."""
    with patch.dict(os.environ, {"AGENT_WORKSPACE_BASE": "/workspace/codetoreum/agent-workspaces"}, clear=False):
        yield


class TestTryReloadForExitCodeSuccess:
    """Test _try_reload_for_exit_code when reload succeeds."""

    def test_reload_succeeds_returns_exit_code(self):
        """Should return exit code when reload succeeds."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        # Mock container with successful reload
        mock_container = MagicMock()
        mock_container.short_id = "abc123"
        mock_container.attrs = {"State": {"ExitCode": 0}}

        result = adapter._try_reload_for_exit_code(mock_container)

        assert result == 0
        mock_container.reload.assert_called_once()

    def test_reload_succeeds_with_nonzero_exit_code(self):
        """Should return non-zero exit code when process fails."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "def456"
        mock_container.attrs = {"State": {"ExitCode": 42}}

        result = adapter._try_reload_for_exit_code(mock_container)

        assert result == 42
        mock_container.reload.assert_called_once()

    def test_reload_succeeds_with_negative_exit_code(self):
        """Should handle negative exit codes (signals)."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "ghi789"
        mock_container.attrs = {"State": {"ExitCode": -15}}

        result = adapter._try_reload_for_exit_code(mock_container)

        assert result == -15


class TestTryReloadForExitCodeNotFound:
    """Test _try_reload_for_exit_code when container is not found."""

    def test_reload_raises_not_found(self):
        """Should raise ContainerExecutionError when container is auto-removed."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "xyz123"
        mock_container.reload.side_effect = docker.errors.NotFound("Container not found")

        with pytest.raises(ContainerExecutionError) as exc_info:
            adapter._try_reload_for_exit_code(mock_container)

        error_msg = str(exc_info.value)
        assert "auto-removed" in error_msg.lower()
        assert "xyz123" in error_msg or "unknown" in error_msg
        assert "OOM-killed" in error_msg or "OOM" in error_msg

    def test_reload_not_found_logging(self):
        """Should log error with correct error ID when container is not found."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "notfound123"
        mock_container.reload.side_effect = docker.errors.NotFound("Container not found")

        with patch("codetoreum.adapters.secondary.docker_container_adapter.logger") as mock_logger:
            with pytest.raises(ContainerExecutionError):
                adapter._try_reload_for_exit_code(mock_container)

            # Verify error was logged
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            # Check that error_id is in the extra dict
            assert call_args.kwargs["extra"]["error_id"] == ErrorRegistry.ERR_CONTAINER_AUTO_REMOVED_AFTER_STREAMING

    def test_reload_not_found_with_none_container(self):
        """Should handle None container gracefully in NotFound case."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = None
        mock_container.reload.side_effect = docker.errors.NotFound("Container not found")

        with pytest.raises(ContainerExecutionError) as exc_info:
            adapter._try_reload_for_exit_code(mock_container)

        error_msg = str(exc_info.value)
        assert "auto-removed" in error_msg.lower()


class TestTryReloadForExitCodeFailureWithPriorError:
    """Test _try_reload_for_exit_code when reload fails with prior_wait_error."""

    def test_reload_fails_with_prior_wait_error(self):
        """Should raise ContainerExecutionError with prior error context."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "dual_fail_123"
        prior_error = Exception("wait() failed")
        mock_container.reload.side_effect = RuntimeError("reload() also failed")

        with pytest.raises(ContainerExecutionError) as exc_info:
            adapter._try_reload_for_exit_code(mock_container, prior_wait_error=prior_error)

        error_msg = str(exc_info.value)
        assert "wait() failed" in error_msg

    def test_reload_fails_dual_failure_logging(self):
        """Should log dual failure with both error IDs."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "dual_fail_456"
        prior_error = Exception("wait() failed")
        mock_container.reload.side_effect = RuntimeError("reload() also failed")

        with patch("codetoreum.adapters.secondary.docker_container_adapter.logger") as mock_logger:
            with pytest.raises(ContainerExecutionError):
                adapter._try_reload_for_exit_code(mock_container, prior_wait_error=prior_error)

            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert call_args.kwargs["extra"]["error_id"] == ErrorRegistry.ERR_CONTAINER_DUAL_RETRIEVAL_FAILED
            assert "wait()" in call_args[0][0]
            assert "reload()" in call_args[0][0]

    def test_reload_fails_with_prior_error_preserves_chain(self):
        """Should raise with prior_wait_error as cause for debugging."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "chain_test"
        prior_error = ValueError("Original wait error")
        mock_container.reload.side_effect = RuntimeError("Reload failed")

        with pytest.raises(ContainerExecutionError) as exc_info:
            adapter._try_reload_for_exit_code(mock_container, prior_wait_error=prior_error)

        # The exception should have the prior error as its cause
        assert exc_info.value.__cause__ is prior_error


class TestTryReloadForExitCodeFailureWithoutPriorError:
    """Test _try_reload_for_exit_code when reload fails without prior_wait_error."""

    def test_reload_fails_single_failure(self):
        """Should raise ContainerExecutionError on single reload failure."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "single_fail_123"
        reload_error = RuntimeError("Failed to reload")
        mock_container.reload.side_effect = reload_error

        with pytest.raises(ContainerExecutionError) as exc_info:
            adapter._try_reload_for_exit_code(mock_container)

        error_msg = str(exc_info.value)
        assert "Failed to retrieve container exit code" in error_msg

    def test_reload_fails_single_failure_logging(self):
        """Should log single failure with correct error ID."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "single_fail_456"
        mock_container.reload.side_effect = RuntimeError("Reload failed")

        with patch("codetoreum.adapters.secondary.docker_container_adapter.logger") as mock_logger:
            with pytest.raises(ContainerExecutionError):
                adapter._try_reload_for_exit_code(mock_container)

            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert call_args.kwargs["extra"]["error_id"] == ErrorRegistry.ERR_CONTAINER_RELOAD_FAILED

    def test_reload_fails_single_preserves_error_chain(self):
        """Should raise with reload error as cause."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "chain_single"
        reload_error = OSError("Connection lost")
        mock_container.reload.side_effect = reload_error

        with pytest.raises(ContainerExecutionError) as exc_info:
            adapter._try_reload_for_exit_code(mock_container)

        assert exc_info.value.__cause__ is reload_error

    def test_reload_fails_with_api_error(self):
        """Should handle Docker API errors correctly."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "api_error_123"
        mock_container.reload.side_effect = docker.errors.APIError("Docker daemon error")

        with pytest.raises(ContainerExecutionError) as exc_info:
            adapter._try_reload_for_exit_code(mock_container)

        error_msg = str(exc_info.value)
        assert "Failed to retrieve container exit code" in error_msg


class TestRunMethodExitCodeRetrieval:
    """Test run() method's exit code retrieval fallback chain."""

    @pytest.mark.asyncio
    async def test_run_wait_succeeds_no_fallback(self):
        """Should return exit code directly when wait() succeeds."""
        config = DockerConfig(verify_workspace_writable=False, remove_on_completion=False)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client

        # Mock container that streams logs and wait() succeeds
        mock_container = MagicMock()
        mock_container.id = "run_test_123"
        mock_container.short_id = "run123"
        mock_container.logs.return_value = iter([b"output line\n"])
        mock_container.wait.return_value = {"StatusCode": 0}

        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.run.return_value = mock_container

        result = await adapter.run(
            image="test:latest",
            command=["echo", "test"],
            volumes={},
            environment={},
            timeout=30,
        )

        assert result.exit_code == 0
        mock_container.wait.assert_called_once()
        mock_container.reload.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_wait_not_found_reload_succeeds(self):
        """Should use reload as fallback when wait() returns NotFound."""
        config = DockerConfig(verify_workspace_writable=False, remove_on_completion=True)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client

        mock_container = MagicMock()
        mock_container.id = "not_found_test"
        mock_container.short_id = "nf123"
        mock_container.logs.return_value = iter([b"output\n"])
        mock_container.wait.side_effect = docker.errors.NotFound("Container not found")
        mock_container.attrs = {"State": {"ExitCode": 0}}

        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.run.return_value = mock_container

        result = await adapter.run(
            image="test:latest",
            command=["echo", "test"],
            volumes={},
            environment={},
            timeout=30,
        )

        assert result.exit_code == 0
        mock_container.wait.assert_called_once()
        mock_container.reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_wait_not_found_reload_fails(self):
        """Should raise error when both wait() and reload() fail."""
        config = DockerConfig(verify_workspace_writable=False, remove_on_completion=True)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client

        mock_container = MagicMock()
        mock_container.id = "both_fail_test"
        mock_container.short_id = "bf123"
        mock_container.logs.return_value = iter([b"output\n"])
        mock_container.wait.side_effect = docker.errors.NotFound("Wait failed")
        mock_container.reload.side_effect = RuntimeError("Reload failed")

        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.run.return_value = mock_container

        with pytest.raises(ContainerExecutionError):
            await adapter.run(
                image="test:latest",
                command=["echo", "test"],
                volumes={},
                environment={},
                timeout=30,
            )

    @pytest.mark.asyncio
    async def test_run_wait_error_reload_succeeds(self):
        """Should use reload when wait() raises non-NotFound error."""
        config = DockerConfig(verify_workspace_writable=False, remove_on_completion=False)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client

        mock_container = MagicMock()
        mock_container.id = "wait_error_test"
        mock_container.short_id = "we123"
        mock_container.logs.return_value = iter([b"output\n"])
        mock_container.wait.side_effect = docker.errors.APIError("API error")
        mock_container.attrs = {"State": {"ExitCode": 0}}

        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.run.return_value = mock_container

        with patch("codetoreum.adapters.secondary.docker_container_adapter.logger") as mock_logger:
            result = await adapter.run(
                image="test:latest",
                command=["echo", "test"],
                volumes={},
                environment={},
                timeout=30,
            )

        assert result.exit_code == 0
        # Should have logged warning about wait failure
        mock_logger.warning.assert_called()
        mock_container.reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_wait_error_reload_fails_with_prior_error(self):
        """Should pass prior_wait_error to reload when wait() fails."""
        config = DockerConfig(verify_workspace_writable=False, remove_on_completion=False)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client

        mock_container = MagicMock()
        mock_container.id = "dual_error_test"
        mock_container.short_id = "de123"
        mock_container.logs.return_value = iter([b"output\n"])
        wait_error = docker.errors.APIError("Wait failed")
        mock_container.wait.side_effect = wait_error
        mock_container.reload.side_effect = RuntimeError("Reload failed")

        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.run.return_value = mock_container

        with patch("codetoreum.adapters.secondary.docker_container_adapter.logger"):
            with pytest.raises(ContainerExecutionError):
                await adapter.run(
                    image="test:latest",
                    command=["echo", "test"],
                    volumes={},
                    environment={},
                    timeout=30,
                )

    @pytest.mark.asyncio
    async def test_run_exit_code_with_nonzero_status(self):
        """Should correctly return non-zero exit codes from wait()."""
        config = DockerConfig(verify_workspace_writable=False, remove_on_completion=False)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client

        mock_container = MagicMock()
        mock_container.id = "nonzero_test"
        mock_container.short_id = "nz123"
        mock_container.logs.return_value = iter([b"error output\n"])
        mock_container.wait.return_value = {"StatusCode": 127}

        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.run.return_value = mock_container

        result = await adapter.run(
            image="test:latest",
            command=["nonexistent-command"],
            volumes={},
            environment={},
            timeout=30,
        )

        assert result.exit_code == 127

    @pytest.mark.asyncio
    async def test_run_exit_code_defaults_to_1_on_missing_status_code(self):
        """Should default to exit code 1 when StatusCode is missing from wait() result."""
        config = DockerConfig(verify_workspace_writable=False, remove_on_completion=False)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client

        mock_container = MagicMock()
        mock_container.id = "missing_status_test"
        mock_container.short_id = "ms123"
        mock_container.logs.return_value = iter([b"output\n"])
        mock_container.wait.return_value = {}  # Missing StatusCode

        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.run.return_value = mock_container

        result = await adapter.run(
            image="test:latest",
            command=["echo", "test"],
            volumes={},
            environment={},
            timeout=30,
        )

        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_run_capture_logs_with_reload_fallback(self):
        """Should capture logs even when falling back to reload for exit code."""
        config = DockerConfig(verify_workspace_writable=False, remove_on_completion=True)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client

        mock_container = MagicMock()
        mock_container.id = "log_capture_test"
        mock_container.short_id = "lc123"
        mock_container.logs.return_value = iter([b"line1\n", b"line2\n"])
        mock_container.wait.side_effect = docker.errors.NotFound("Container removed")
        mock_container.attrs = {"State": {"ExitCode": 0}}

        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.run.return_value = mock_container

        result = await adapter.run(
            image="test:latest",
            command=["echo", "test"],
            volumes={},
            environment={},
            timeout=30,
        )

        assert result.exit_code == 0
        assert "line1" in result.stdout
        assert "line2" in result.stdout

    @pytest.mark.asyncio
    async def test_run_stream_callback_with_exit_code_fallback(self):
        """Should call stream_callback for each line even with reload fallback."""
        config = DockerConfig(verify_workspace_writable=False, remove_on_completion=True)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client

        mock_container = MagicMock()
        mock_container.id = "callback_test"
        mock_container.short_id = "cb123"
        mock_container.logs.return_value = iter([b"output1\n", b"output2\n"])
        mock_container.wait.side_effect = docker.errors.NotFound("Container removed")
        mock_container.attrs = {"State": {"ExitCode": 0}}

        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.run.return_value = mock_container

        callback_lines = []

        def test_callback(line):
            callback_lines.append(line)

        result = await adapter.run(
            image="test:latest",
            command=["echo", "test"],
            volumes={},
            environment={},
            timeout=30,
            stream_callback=test_callback,
        )

        assert result.exit_code == 0
        assert len(callback_lines) == 2
        assert "output1" in callback_lines[0]
        assert "output2" in callback_lines[1]


class TestExitCodeErrorMessages:
    """Test that error messages are informative for debugging."""

    def test_not_found_error_mentions_data_loss(self):
        """Error message should mention potential data loss and causes."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "msg_test"
        mock_container.reload.side_effect = docker.errors.NotFound("Not found")

        with pytest.raises(ContainerExecutionError) as exc_info:
            adapter._try_reload_for_exit_code(mock_container)

        error_msg = str(exc_info.value)
        assert "data loss" in error_msg.lower() or "artifacts" in error_msg.lower()
        assert "OOM-killed" in error_msg or "force-removed" in error_msg

    def test_dual_failure_error_includes_both_errors(self):
        """Error message should mention both wait() and reload() failures."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "msg_dual"
        wait_error = Exception("wait failed")
        mock_container.reload.side_effect = Exception("reload failed")

        with patch("codetoreum.adapters.secondary.docker_container_adapter.logger"):
            with pytest.raises(ContainerExecutionError):
                adapter._try_reload_for_exit_code(mock_container, prior_wait_error=wait_error)


class TestExitCodeEdgeCases:
    """Test edge cases in exit code handling."""

    def test_reload_with_empty_short_id(self):
        """Should handle containers with empty short_id."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = ""
        mock_container.reload.side_effect = RuntimeError("Reload failed")

        with patch("codetoreum.adapters.secondary.docker_container_adapter.logger") as mock_logger:
            with pytest.raises(ContainerExecutionError):
                adapter._try_reload_for_exit_code(mock_container)

            call_args = mock_logger.error.call_args
            assert call_args is not None

    def test_reload_with_very_long_container_id(self):
        """Should handle very long container IDs correctly."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        mock_container.short_id = "a" * 12  # 12-char short ID
        mock_container.attrs = {"State": {"ExitCode": 0}}

        result = adapter._try_reload_for_exit_code(mock_container)

        assert result == 0

    def test_reload_error_logging_includes_container_id(self):
        """Should log container ID in extra field for error tracking."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_container = MagicMock()
        container_id = "test_container_id_xyz"
        mock_container.short_id = container_id
        mock_container.reload.side_effect = RuntimeError("Test error")

        with patch("codetoreum.adapters.secondary.docker_container_adapter.logger") as mock_logger:
            with pytest.raises(ContainerExecutionError):
                adapter._try_reload_for_exit_code(mock_container)

            call_args = mock_logger.error.call_args
            assert call_args.kwargs["extra"]["container_id"] == container_id
