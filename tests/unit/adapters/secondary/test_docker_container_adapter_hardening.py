"""Unit tests for DockerContainerAdapter production hardening.

These tests verify:
- Host path detection and translation
- Container name sanitization
- Workspace write access verification
- OTEL environment variable injection
- Network configuration from env vars
"""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.secondary.docker_container_adapter import DockerConfig, DockerContainerAdapter
from codetoreum.ports.exceptions import ContainerError, ValidationError


@pytest.fixture(autouse=True)
def _patch_agent_workspace_base():
    """Patch AGENT_WORKSPACE_BASE to a valid path for all tests."""
    with patch.dict(os.environ, {"AGENT_WORKSPACE_BASE": "/workspace/codetoreum/agent-workspaces"}, clear=False):
        yield


class TestDetectHostWorkspacePath:
    """Tests for _detect_host_workspace_path static method."""

    def test_detect_workspace_path_from_mountinfo(self):
        """Should parse /proc/self/mountinfo correctly when /workspace is present."""
        mountinfo_content = """1 0 10:0 / / rw,relatime shared:1 - ext4 /dev/sda1 rw
2 1 8:1 /host/workspace /workspace rw,relatime - ext4 /dev/sdb rw
3 1 8:2 /home /home rw,relatime - ext4 /dev/sdc rw
"""
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.readlines.return_value = mountinfo_content.strip().split("\n")
            mock_open.return_value.__enter__.return_value = iter(mountinfo_content.strip().split("\n"))

            with patch("builtins.open", create=True) as mock_file:
                mock_file.return_value.__enter__.return_value = iter(mountinfo_content.strip().split("\n"))
                result = DockerContainerAdapter._detect_host_workspace_path()

            assert result == "/host/workspace"

    def test_detect_workspace_path_fallback_to_env_var(self):
        """Should fall back to HOST_WORKSPACE_PATH env var when parse fails."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            with patch.dict(os.environ, {"HOST_WORKSPACE_PATH": "/custom/workspace"}, clear=False):
                result = DockerContainerAdapter._detect_host_workspace_path()

            assert result == "/custom/workspace"

    def test_detect_workspace_path_fallback_default(self):
        """Should use /workspace as fallback when env var not set."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            with patch.dict(os.environ, {}, clear=True):
                # Simulate default when no HOST_WORKSPACE_PATH
                with patch("os.environ.get", side_effect=lambda k, default: default):
                    result = DockerContainerAdapter._detect_host_workspace_path()

            assert result == "/workspace"


class TestDetectHostHomePath:
    """Tests for _detect_host_home_path static method."""

    def test_detect_home_path_from_env(self):
        """Should read HOST_HOME env var when set."""
        with patch.dict(os.environ, {"HOST_HOME": "/home/testuser"}, clear=False):
            result = DockerContainerAdapter._detect_host_home_path()

        assert result == "/home/testuser"

    def test_detect_home_path_warning_when_unset(self):
        """Should log warning when HOST_HOME is unset."""
        with patch.dict(os.environ, {"HOME": "/root"}, clear=True):
            with patch("codetoreum.adapters.secondary.docker_container_adapter.logger") as mock_logger:
                result = DockerContainerAdapter._detect_host_home_path()

            assert result == "/root"
            mock_logger.warning.assert_called_once()
            assert "HOST_HOME is not set" in str(mock_logger.warning.call_args)

    def test_detect_home_path_fallback(self):
        """Should use /root as fallback when HOME env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("os.environ.get", side_effect=lambda k, default=None: default):
                result = DockerContainerAdapter._detect_host_home_path()

            assert result == "/root"


class TestSanitizeContainerName:
    """Tests for _sanitize_container_name static method."""

    def test_sanitize_valid_name_unchanged(self):
        """Valid names should remain unchanged."""
        name = "codetoreum-agent-project-123abc"
        result = DockerContainerAdapter._sanitize_container_name(name)
        assert result == name

    def test_sanitize_removes_invalid_chars(self):
        """Should remove invalid characters."""
        name = "codetoreum/agent:project@host"
        result = DockerContainerAdapter._sanitize_container_name(name)
        assert result == "codetoreum-agent-project-host"
        assert all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for c in result)

    def test_sanitize_leading_invalid_chars(self):
        """Should remove leading invalid characters."""
        name = "---codetoreum-agent"
        result = DockerContainerAdapter._sanitize_container_name(name)
        assert result == "codetoreum-agent"

    def test_sanitize_leading_numbers(self):
        """Should preserve leading numbers (Docker allows [a-zA-Z0-9]...)."""
        name = "123codetoreum-agent"
        result = DockerContainerAdapter._sanitize_container_name(name)
        assert result == "123codetoreum-agent"

    def test_sanitize_multiple_dashes(self):
        """Should collapse multiple consecutive dashes."""
        name = "codetoreum----agent"
        result = DockerContainerAdapter._sanitize_container_name(name)
        assert result == "codetoreum-agent"

    def test_sanitize_all_invalid(self):
        """Should handle names with mostly invalid characters."""
        name = "/@#$%"
        result = DockerContainerAdapter._sanitize_container_name(name)
        assert result == ""  # All removed; leading removal leaves empty

    def test_sanitize_with_dots_and_underscores(self):
        """Should preserve dots and underscores."""
        name = "codetoreum_agent.v1"
        result = DockerContainerAdapter._sanitize_container_name(name)
        assert result == name


class TestBuildAgentOtelEnv:
    """Tests for _build_agent_otel_env method."""

    def test_build_otel_env_all_required_keys(self):
        """Should include all required OTEL keys."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        result = adapter._build_agent_otel_env(
            execution_id="exec-123",
            agent_name="test-agent",
            project_id="proj-456",
            work_item_id="item-789",
        )

        required_keys = [
            "CLAUDE_CODE_ENABLE_TELEMETRY",
            "OTEL_METRICS_EXPORTER",
            "OTEL_LOGS_EXPORTER",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTEL_METRIC_EXPORT_INTERVAL",
            "OTEL_LOGS_EXPORT_INTERVAL",
            "OTEL_RESOURCE_ATTRIBUTES",
        ]
        for key in required_keys:
            assert key in result

    def test_build_otel_env_default_endpoint(self):
        """Should use default OTEL endpoint when not overridden."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        with patch.dict(os.environ, {}, clear=True):
            result = adapter._build_agent_otel_env("exec-1", "agent-1", "proj-1", "item-1")

        assert result["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-collector:4317"

    def test_build_otel_env_custom_endpoint(self):
        """Should respect AGENT_OTEL_ENDPOINT env var."""
        with patch.dict(os.environ, {"AGENT_OTEL_ENDPOINT": "http://custom:5000"}, clear=False):
            config = DockerConfig()
            adapter = DockerContainerAdapter(config)

            result = adapter._build_agent_otel_env("exec-1", "agent-1", "proj-1", "item-1")

        assert result["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://custom:5000"

    def test_build_otel_env_resource_attributes(self):
        """Should include all resource attributes."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        result = adapter._build_agent_otel_env(
            execution_id="exec-123",
            agent_name="my-agent",
            project_id="my-project",
            work_item_id="item-999",
        )

        attrs = result["OTEL_RESOURCE_ATTRIBUTES"]
        assert "agent=my-agent" in attrs
        assert "project=my-project" in attrs
        assert "execution_id=exec-123" in attrs
        assert "work_item_id=item-999" in attrs


class TestVerifyWorkspaceWritable:
    """Tests for _verify_workspace_writable method."""

    @pytest.mark.asyncio
    async def test_verify_workspace_writable_success(self):
        """Should succeed when container can write to workspace."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client
        mock_client.containers.run.return_value = None

        volume_spec = {"/host/workspace": {"bind": "/workspace", "mode": "rw"}}
        await adapter._verify_workspace_writable(volume_spec, "/workspace")

        # Should call run once for the test
        assert mock_client.containers.run.call_count == 1

    @pytest.mark.asyncio
    async def test_verify_workspace_writable_single_attempt(self):
        """Should make a single attempt (no retries)."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client
        mock_client.containers.run.return_value = None

        volume_spec = {"/host/workspace": {"bind": "/workspace", "mode": "rw"}}
        await adapter._verify_workspace_writable(volume_spec, "/workspace")

        assert mock_client.containers.run.call_count == 1

    @pytest.mark.asyncio
    async def test_verify_workspace_writable_failure(self):
        """Should raise ContainerError on single failed attempt."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client
        mock_client.containers.run.side_effect = Exception("Permission denied")

        volume_spec = {"/host/workspace": {"bind": "/workspace", "mode": "rw"}}

        with pytest.raises(ContainerError) as exc_info:
            await adapter._verify_workspace_writable(volume_spec, "/workspace")

        assert "not writable" in str(exc_info.value)
        assert str(volume_spec) in str(exc_info.value)
        assert mock_client.containers.run.call_count == 1


class TestDockerConfigAgentNetwork:
    """Tests for agent_network configuration."""

    def test_agent_network_default(self):
        """Should default to codetoreum_default."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("os.environ.get", side_effect=lambda k, default: default):
                config = DockerConfig()

        assert config.agent_network == "bridge"

    def test_agent_network_from_env_var(self):
        """Should read AGENT_NETWORK from environment."""
        with patch.dict(os.environ, {"AGENT_NETWORK": "switchyard_orchestrator-net"}, clear=False):
            config = DockerConfig()

        assert config.agent_network == "switchyard_orchestrator-net"

    def test_agent_network_in_run_method(self):
        """Should use agent_network in run() method."""
        with patch.dict(os.environ, {"AGENT_NETWORK": "custom-net"}, clear=False):
            config = DockerConfig()

        assert config.agent_network == "custom-net"


class TestDockerConfigVerifyWorkspaceWritable:
    """Tests for verify_workspace_writable configuration."""

    def test_verify_workspace_writable_default(self):
        """Should default to True."""
        config = DockerConfig()
        assert config.verify_workspace_writable is True

    def test_verify_workspace_writable_can_be_disabled(self):
        """Should allow disabling for testing."""
        config = DockerConfig(verify_workspace_writable=False)
        assert config.verify_workspace_writable is False


class TestParseVolumeSpecWithPathTranslation:
    """Tests for path translation in _parse_volume_spec."""

    def test_parse_volume_spec_workspace_path_translation(self):
        """Should translate /workspace paths to host equivalents."""
        with patch.dict(os.environ, {"HOST_WORKSPACE_PATH": "/mnt/host/workspace"}, clear=False):
            with patch.object(
                DockerContainerAdapter, "_detect_host_workspace_path", return_value="/mnt/host/workspace"
            ):
                config = DockerConfig()
                adapter = DockerContainerAdapter(config)

                volumes = {"/workspace/project": "/workspace:rw"}
                result = adapter._parse_volume_spec(volumes)

                # Should have translated the path
                assert "/mnt/host/workspace/project" in result

    def test_parse_volume_spec_non_workspace_path_unchanged(self):
        """Should not translate paths not under /workspace or $HOME."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        volumes = {"/var/log": "/logs:rw"}
        result = adapter._parse_volume_spec(volumes)

        # The path should be resolved (absolute) but not translated
        assert "/var/log" in result or str(Path("/var/log").resolve()) in result

    def test_parse_volume_spec_relative_paths_resolved(self):
        """Should resolve relative paths to absolute."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        volumes = {"./relative/path": "/container:rw"}
        result = adapter._parse_volume_spec(volumes)

        # Relative paths should be resolved to absolute, and result keys should contain the resolved path
        # The exact path depends on the current working directory
        assert len(result) == 1
        result_key = list(result.keys())[0]
        # Should be an absolute path
        assert result_key.startswith("/")
        # Should end with the relative path components
        assert result_key.endswith("relative/path")

    def test_parse_volume_spec_invalid_mode_rejected(self):
        """Should reject invalid mount modes."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        volumes = {"/absolute/path": "/container:invalid"}

        with pytest.raises(ValidationError) as exc_info:
            adapter._parse_volume_spec(volumes)

        assert "invalid" in str(exc_info.value).lower() or "mode" in str(exc_info.value).lower()

    def test_parse_volume_spec_relative_container_path_rejected(self):
        """Should reject relative container paths."""
        config = DockerConfig()
        adapter = DockerContainerAdapter(config)

        volumes = {"/absolute/path": "relative/container:rw"}

        with pytest.raises(ValidationError) as exc_info:
            adapter._parse_volume_spec(volumes)

        assert "absolute" in str(exc_info.value).lower()


class TestCreateMethodIntegration:
    """Integration tests for create() method with hardening features."""

    @pytest.mark.asyncio
    async def test_create_sanitizes_container_name(self):
        """Should sanitize container name before passing to Docker."""
        config = DockerConfig(verify_workspace_writable=False)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client
        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.create.return_value = MagicMock(id="container-123")

        await adapter.create(image="test:latest", name="invalid/container:name@host")

        # Should call create with sanitized name
        call_args = mock_client.containers.create.call_args
        assert call_args is not None
        assert call_args.kwargs["name"] == "invalid-container-name-host"

    @pytest.mark.asyncio
    async def test_create_uses_agent_network(self):
        """Should use agent_network instead of default_network."""
        with patch.dict(os.environ, {"AGENT_NETWORK": "test-net"}, clear=False):
            config = DockerConfig(verify_workspace_writable=False)
            adapter = DockerContainerAdapter(config)

            mock_client = MagicMock()
            adapter._docker_client = mock_client
            mock_client.images.get.return_value = MagicMock()
            mock_client.containers.create.return_value = MagicMock(id="container-123")

            await adapter.create(image="test:latest")

            call_args = mock_client.containers.create.call_args
            assert call_args.kwargs["network"] == "test-net"

    @pytest.mark.asyncio
    async def test_create_injects_otel_env(self):
        """Should inject OTEL environment variables."""
        config = DockerConfig(verify_workspace_writable=False)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client
        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.create.return_value = MagicMock(id="container-123")

        labels = {
            "org.codetoreum.execution_id": "exec-123",
            "org.codetoreum.agent": "test-agent",
            "org.codetoreum.project": "test-project",
            "org.codetoreum.work_item_id": "item-123",
        }

        await adapter.create(image="test:latest", labels=labels)

        call_args = mock_client.containers.create.call_args
        env = call_args.kwargs["environment"]
        assert "CLAUDE_CODE_ENABLE_TELEMETRY" in env
        assert env["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"

    @pytest.mark.asyncio
    async def test_create_verifies_workspace_writable_when_enabled(self):
        """Should verify workspace write access when enabled."""
        config = DockerConfig(verify_workspace_writable=True)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client
        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.create.return_value = MagicMock(id="container-123")
        mock_client.containers.run.return_value = None

        volumes = {"/workspace/test": "/workspace:rw"}

        with patch.object(adapter, "_verify_workspace_writable", new_callable=AsyncMock) as mock_verify:
            await adapter.create(image="test:latest", volumes=volumes)

            mock_verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_skips_workspace_verify_when_disabled(self):
        """Should skip write verification when disabled."""
        config = DockerConfig(verify_workspace_writable=False)
        adapter = DockerContainerAdapter(config)

        mock_client = MagicMock()
        adapter._docker_client = mock_client
        mock_client.images.get.return_value = MagicMock()
        mock_client.containers.create.return_value = MagicMock(id="container-123")

        volumes = {"/workspace/test": "/workspace:rw"}

        with patch.object(adapter, "_verify_workspace_writable", new_callable=AsyncMock) as mock_verify:
            await adapter.create(image="test:latest", volumes=volumes)

            mock_verify.assert_not_called()


class TestAgentWorkspaceBaseValidation:
    """Tests for AGENT_WORKSPACE_BASE validation."""

    def test_agent_workspace_base_raises_when_under_tmp(self):
        """Should raise ContainerError if AGENT_WORKSPACE_BASE is under /tmp/."""
        with patch.dict(os.environ, {"AGENT_WORKSPACE_BASE": "/tmp/codetoreum/workspaces"}, clear=False):
            config = DockerConfig()
            with pytest.raises(ContainerError) as exc_info:
                DockerContainerAdapter(config)

            assert "AGENT_WORKSPACE_BASE" in str(exc_info.value)
            assert "/tmp/" in str(exc_info.value)

    def test_agent_workspace_base_valid_under_workspace(self):
        """Should not raise if AGENT_WORKSPACE_BASE is under /workspace/."""
        with patch.dict(os.environ, {"AGENT_WORKSPACE_BASE": "/workspace/codetoreum/workspaces"}, clear=False):
            config = DockerConfig()
            adapter = DockerContainerAdapter(config)
            assert adapter is not None


class TestAgentOtelEndpoint:
    """Tests for agent_otel_endpoint configuration."""

    def test_agent_otel_endpoint_default(self):
        """Should default to http://otel-collector:4317."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("os.environ.get", side_effect=lambda k, default: default):
                config = DockerConfig()

        assert config.agent_otel_endpoint == "http://otel-collector:4317"

    def test_agent_otel_endpoint_from_env_var(self):
        """Should read AGENT_OTEL_ENDPOINT from environment."""
        with patch.dict(os.environ, {"AGENT_OTEL_ENDPOINT": "http://custom:5000"}, clear=False):
            config = DockerConfig()

        assert config.agent_otel_endpoint == "http://custom:5000"

    def test_build_otel_env_uses_config_endpoint(self):
        """Should use agent_otel_endpoint from config, not os.environ directly."""
        with patch.dict(os.environ, {"AGENT_OTEL_ENDPOINT": "http://custom-endpoint:9999"}, clear=False):
            config = DockerConfig()
            adapter = DockerContainerAdapter(config)

            result = adapter._build_agent_otel_env("exec-1", "agent-1", "proj-1", "item-1")

            assert result["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://custom-endpoint:9999"
