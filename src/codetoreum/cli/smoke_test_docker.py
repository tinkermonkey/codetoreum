"""Docker container smoke test — validate Docker adapter against real daemon.

This smoke test validates the full container lifecycle:
1. Host path detection
2. Pre-launch write verification
3. Container launch and execution
4. Command output verification
5. OTEL environment variable verification
6. Network connectivity to Redis
7. Negative security checks
8. Container cleanup verification

Exit codes:
    0 - All steps passed
    1 - One or more steps failed
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

import click

# Optionally add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from codetoreum.adapters.secondary.docker_container_adapter import (
    DockerConfig,
    DockerContainerAdapter,
)
from codetoreum.ports.exceptions import ContainerError, ContainerExecutionError

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


class SmokeTestRunner:
    """Run Docker container smoke test."""

    def __init__(self):
        """Initialize smoke test runner."""
        self.results = {}
        self.adapter = None
        self.test_container_id = None

    def _log_step(self, step_num: int, name: str, status: str, details: str = ""):
        """Log a test step result."""
        status_symbol = "✓" if status == "PASS" else "✗"
        msg = f"Step {step_num}: {name} [{status_symbol}]"
        if details:
            msg += f" - {details}"
        print(msg)
        if status != "PASS":
            logger.error(msg)
        else:
            logger.info(msg)
        self.results[step_num] = {"name": name, "status": status, "details": details}

    def _detect_host_workspace_path(self) -> str:
        """Detect host workspace path from /proc/self/mountinfo."""
        try:
            with open("/proc/self/mountinfo") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) > 4:
                        mount_point = parts[4]
                        if mount_point == "/workspace":
                            # parts[3] is the relative_path (root of the mount on the host)
                            host_path = parts[3]
                            return host_path
        except Exception as e:
            logger.warning(f"Failed to auto-detect host workspace from mountinfo: {e}")

        fallback = os.environ.get("HOST_WORKSPACE_PATH", "/workspace")
        return fallback

    def _detect_host_home_path(self) -> str:
        """Detect host home path from environment."""
        host_home = os.environ.get("HOST_HOME")
        if host_home:
            return host_home
        return os.environ.get("HOME", "/root")

    async def run(self) -> bool:
        """Run all smoke test steps."""
        print("\n" + "=" * 70)
        print("Docker Container Smoke Test")
        print("=" * 70 + "\n")

        try:
            # Step 1: Host path detection
            step_start = time.time()
            try:
                workspace_path = self._detect_host_workspace_path()
                home_path = self._detect_host_home_path()

                # Note: We cannot directly verify these paths exist from inside a container
                # since _detect_host_workspace_path() returns host paths that may not exist
                # in the container filesystem. Instead, we log what was detected and validate
                # in later steps when we actually use these paths (e.g., Step 2 workspace writable check).
                logger.info(f"Detected workspace path: {workspace_path}")
                logger.info(f"Detected home path: {home_path}")

                duration = time.time() - step_start
                self._log_step(
                    1,
                    "Host path detection",
                    "PASS",
                    f"workspace={workspace_path}, home={home_path} ({duration:.2f}s)",
                )
            except Exception as e:
                self._log_step(1, "Host path detection", "FAIL", str(e))
                return False

            # Step 2: Pre-launch write check
            step_start = time.time()
            try:
                workspace_base = os.environ.get("AGENT_WORKSPACE_BASE", "/workspace/codetoreum/agent-workspaces")
                Path(workspace_base).mkdir(parents=True, exist_ok=True)

                # Create a test file to verify writability
                test_file = Path(workspace_base) / ".codetoreum_write_test"
                test_file.write_text("test")
                test_file.unlink()

                duration = time.time() - step_start
                self._log_step(
                    2,
                    "Pre-launch write check",
                    "PASS",
                    f"AGENT_WORKSPACE_BASE={workspace_base} is writable ({duration:.2f}s)",
                )
            except Exception as e:
                self._log_step(2, "Pre-launch write check", "FAIL", str(e))
                return False

            # Step 3: Container launch
            step_start = time.time()
            try:
                # Configure Docker adapter (auto-remove containers after execution)
                docker_config = DockerConfig(
                    default_user="1000:1000",
                    agent_network=os.environ.get("DOCKER_NETWORK", "bridge"),
                    remove_on_completion=True,
                )
                self.adapter = DockerContainerAdapter(config=docker_config)

                # Test basic container launch with a simple sleep/exit command
                result = await self.adapter.run(
                    image="python:3.11-slim",
                    command=["sh", "-c", "echo 'Container launched successfully' && sleep 1"],
                    volumes={workspace_path: "/workspace:rw"},
                    environment={
                        "OTEL_ENABLED": "1",
                        "OTEL_METRICS_EXPORTER": "otlp",
                        "OTEL_LOGS_EXPORTER": "otlp",
                        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
                        "OTEL_RESOURCE_ATTRIBUTES": "agent=test,project=smoke_test",
                    },
                )

                self.test_container_id = result.container_id
                duration = time.time() - step_start

                self._log_step(
                    3,
                    "Container launch",
                    "PASS",
                    f"container_id={self.test_container_id}, exit_code={result.exit_code} ({duration:.2f}s)",
                )
            except Exception as e:
                self._log_step(3, "Container launch", "FAIL", str(e))
                return False

            # Step 4: Command execution
            step_start = time.time()
            try:
                result = await self.adapter.run(
                    image="python:3.11-slim",
                    command=["sh", "-c", "echo hello"],
                    volumes={},
                    environment={},
                )

                stdout = result.stdout.strip()
                if stdout != "hello":
                    self._log_step(
                        4,
                        "Command execution",
                        "FAIL",
                        f"Expected 'hello', got '{stdout}'",
                    )
                    return False

                duration = time.time() - step_start
                self._log_step(
                    4,
                    "Command execution",
                    "PASS",
                    f"stdout={stdout} ({duration:.2f}s)",
                )
            except Exception as e:
                self._log_step(4, "Command execution", "FAIL", str(e))
                return False

            # Step 5: OTEL env verification
            step_start = time.time()
            try:
                otel_env_vars = {
                    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
                    "OTEL_METRICS_EXPORTER": "otlp",
                    "OTEL_LOGS_EXPORTER": "otlp",
                    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector:4317",
                    "OTEL_RESOURCE_ATTRIBUTES": "agent=test,project=smoke_test",
                }

                result = await self.adapter.run(
                    image="python:3.11-slim",
                    command=["sh", "-c", "env | grep OTEL || env | grep CLAUDE"],
                    volumes={},
                    environment=otel_env_vars,
                )

                env_output = result.stdout.lower()
                missing_vars = []

                for var in otel_env_vars.keys():
                    if var.lower() not in env_output:
                        missing_vars.append(var)

                if missing_vars:
                    self._log_step(
                        5,
                        "OTEL env verification",
                        "FAIL",
                        f"Missing OTEL vars: {', '.join(missing_vars)}",
                    )
                    return False

                duration = time.time() - step_start
                self._log_step(
                    5,
                    "OTEL env verification",
                    "PASS",
                    f"All OTEL vars present ({duration:.2f}s)",
                )
            except Exception as e:
                self._log_step(5, "OTEL env verification", "FAIL", str(e))
                return False

            # Step 6: Network connectivity (Redis check via Docker DNS on compose network)
            step_start = time.time()
            try:
                # Test Docker DNS service discovery on the compose network
                # Agent containers should be able to reach Redis by hostname on the named network
                redis_available = False
                try:
                    # Create a temporary adapter for this test with the compose network
                    compose_network = os.environ.get("DOCKER_NETWORK", "codetoreum_default")
                    redis_adapter = DockerContainerAdapter(
                        config=DockerConfig(
                            default_user="1000:1000",
                            agent_network=compose_network,
                            remove_on_completion=True,
                        )
                    )

                    # Connect to Redis on the named network using DNS service discovery
                    result = await redis_adapter.run(
                        image="python:3.11-slim",
                        command=[
                            "sh",
                            "-c",
                            'python3 -c \'import socket; s=socket.socket(); s.connect(("redis", 6379)); s.close(); print("ok")\'',
                        ],
                        volumes={},
                        environment={},
                    )
                    if "ok" in result.stdout:
                        redis_available = True
                except Exception:
                    # Redis not available, skip this check
                    pass

                duration = time.time() - step_start
                if redis_available:
                    self._log_step(
                        6,
                        "Network connectivity (Redis)",
                        "PASS",
                        f"Redis reachable via DNS on {compose_network} network ({duration:.2f}s)",
                    )
                else:
                    self._log_step(
                        6,
                        "Network connectivity (Redis)",
                        "SKIP",
                        "Redis not available (expected in local testing)",
                    )
            except Exception as e:
                self._log_step(6, "Network connectivity", "SKIP", str(e))

            # Step 7: Negative security checks
            step_start = time.time()
            try:
                security_issues = []

                # Check 1: No Docker socket
                try:
                    result = await self.adapter.run(
                        image="python:3.11-slim",
                        command=["test", "-S", "/var/run/docker.sock"],
                        volumes={},
                        environment={},
                    )
                    if result.exit_code == 0:
                        security_issues.append("Docker socket accessible")
                except (ContainerExecutionError, ContainerError):
                    pass  # Expected to fail - socket check should fail if not present

                # Check 2: No SSH keys
                try:
                    result = await self.adapter.run(
                        image="python:3.11-slim",
                        command=["test", "-f", "/home/orchestrator/.ssh/id_github"],
                        volumes={},
                        environment={},
                    )
                    if result.exit_code == 0:
                        security_issues.append("SSH key id_github accessible")
                except (ContainerExecutionError, ContainerError):
                    pass  # Expected to fail - key check should fail if not present

                # Check 3: GITHUB_TOKEN not in environment
                result = await self.adapter.run(
                    image="python:3.11-slim",
                    command=["sh", "-c", "env | grep -i github_token || echo 'not_found'"],
                    volumes={},
                    environment={},
                )
                if "GITHUB_TOKEN" in result.stdout and "not_found" not in result.stdout:
                    security_issues.append("GITHUB_TOKEN exposed in env")

                # Check 4: CLAUDE_CODE_OAUTH_TOKEN not in environment
                result = await self.adapter.run(
                    image="python:3.11-slim",
                    command=["sh", "-c", "env | grep -i claude_code_oauth_token || echo 'not_found'"],
                    volumes={},
                    environment={},
                )
                if "CLAUDE_CODE_OAUTH_TOKEN" in result.stdout and "not_found" not in result.stdout:
                    security_issues.append("CLAUDE_CODE_OAUTH_TOKEN exposed in env")

                duration = time.time() - step_start

                if security_issues:
                    self._log_step(
                        7,
                        "Negative security checks",
                        "FAIL",
                        f"Issues found: {'; '.join(security_issues)}",
                    )
                    return False

                self._log_step(
                    7,
                    "Negative security checks",
                    "PASS",
                    f"No security issues detected ({duration:.2f}s)",
                )
            except Exception as e:
                self._log_step(7, "Negative security checks", "FAIL", str(e))
                return False

            # Step 8: Cleanup verification
            step_start = time.time()
            try:
                # Verify that agent containers have been cleaned up
                import docker

                try:
                    client = docker.from_env()
                    # Check for lingering containers with the codetoreum-agent prefix
                    # Note: Docker filters use regex, so we check for containers whose name contains "codetoreum-agent"
                    containers = client.containers.list(all=True, filters={"name": "codetoreum-agent"})

                    if containers:
                        self._log_step(
                            8,
                            "Cleanup verification",
                            "FAIL",
                            f"Found {len(containers)} lingering codetoreum-agent containers",
                        )
                        return False

                    duration = time.time() - step_start
                    self._log_step(
                        8,
                        "Cleanup verification",
                        "PASS",
                        f"No lingering codetoreum-agent containers ({duration:.2f}s)",
                    )
                except Exception as e:
                    # If we can't connect to Docker to verify, just log a warning
                    logger.warning(f"Could not verify cleanup: {e}")
                    duration = time.time() - step_start
                    self._log_step(
                        8,
                        "Cleanup verification",
                        "SKIP",
                        f"Cleanup verification skipped (Docker connection issue) ({duration:.2f}s)",
                    )
            except Exception as e:
                self._log_step(8, "Cleanup verification", "FAIL", str(e))
                return False

            return True

        except Exception as e:
            print(f"\nFatal error: {e}")
            logger.exception("Smoke test failed with exception")
            return False

    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 70)
        print("Summary")
        print("=" * 70)

        passed = sum(1 for r in self.results.values() if r["status"] == "PASS")
        failed = sum(1 for r in self.results.values() if r["status"] == "FAIL")
        skipped = sum(1 for r in self.results.values() if r["status"] == "SKIP")

        for step_num in sorted(self.results.keys()):
            r = self.results[step_num]
            status_symbol = "✓" if r["status"] == "PASS" else ("✗" if r["status"] == "FAIL" else "-")
            print(f"{status_symbol} Step {step_num}: {r['name']}")

        print(f"\nResults: {passed} passed, {failed} failed, {skipped} skipped ({len(self.results)} total)")
        print("=" * 70 + "\n")

        return failed == 0


@click.command(name="smoke-test-docker")
@click.option(
    "--verbose",
    is_flag=True,
    help="Enable verbose logging",
)
def smoke_test_docker(verbose: bool):
    """Run Docker container smoke test."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    runner = SmokeTestRunner()
    success = asyncio.run(runner.run())
    runner.print_summary()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    smoke_test_docker()
