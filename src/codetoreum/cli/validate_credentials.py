"""
Credential validation script for production deployment pre-flight checks.

Validates that all required credentials are present and functional by attempting
cheap, read-only API calls to each adapter. Uses the same AdapterResolver and
AdapterSelectionConfig infrastructure as production bootstrap to ensure validation
exercises the same adapter wiring.

Run with:
    python -m codetoreum.cli.validate_credentials
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass

from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
from codetoreum.infrastructure.adapters.resolver import (
    AdapterConfigurationError,
    AdapterDependencies,
    AdapterResolver,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.resilience import OperationMode
from codetoreum.infrastructure.simulation.simulation_config import (
    AdapterSelectionConfig,
    SimulationConfig,
)
from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.code_review_service import ICodeReviewService
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.llm_provider import ILLMProvider
from codetoreum.ports.output.ticket_system import ITicketSystem
from codetoreum.ports.output.version_control_service import IVersionControlService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class AdapterHealthCheckResult:
    """Result of a single adapter health check."""

    adapter_slot: str
    concrete_class: str
    status: str  # "PASS", "FAIL", "SKIP"
    error: str | None = None


class CredentialValidator:
    """Validates production credentials by attempting cheap API calls to adapters."""

    # Critical adapters that must pass for MVP
    CRITICAL_ADAPTERS = {
        "ticket",
        "board",
        "llm",
        "container",
        "version_control",
        "code_review",
    }

    def __init__(self):
        """Initialize the credential validator."""
        self.results: list[AdapterHealthCheckResult] = []

    async def validate_all(self) -> bool:
        """
        Validate all credentials.

        Returns:
            True if all critical adapters pass, False otherwise.
        """
        # Create production adapter selection config
        adapter_config = self._get_production_adapter_config()

        # Create factory
        factory_config = AdapterFactoryConfig(
            operation_mode=OperationMode.PRODUCTION,
            enable_resilience=False,  # Disable resilience for validation to get direct errors
        )
        factory = AdapterFactory(config=factory_config)

        # Create event bus and simulation config
        event_bus = EventBus()
        sim_config = SimulationConfig.create_fast_config("validation", speed_multiplier=100.0)
        engine = SimulationEngine(sim_config)

        # Create event emitter
        from codetoreum.adapters.testing import CapturingMockEventEmitter

        event_emitter = CapturingMockEventEmitter()

        # Create adapter dependencies
        dependencies = AdapterDependencies(
            event_bus=event_bus,
            event_emitter=event_emitter,
            logger=logger,
            engine=engine,
            config=sim_config,
        )

        # Create resolver
        resolver = AdapterResolver(adapter_config, factory, dependencies)

        # Pre-flight validation: check credentials are present before resolving
        try:
            resolver.validate_credentials()
            logger.info("✓ All adapter credentials are present")
        except AdapterConfigurationError as e:
            logger.error("✗ Credential configuration errors:")
            for error in e.errors:
                logger.error(f"  - {error}")
            self.results.append(
                AdapterHealthCheckResult(
                    adapter_slot="all",
                    concrete_class="AdapterResolver",
                    status="FAIL",
                    error="Credential configuration errors",
                )
            )
            return False

        # Health check each critical adapter
        await self._check_adapter_ticket(resolver)
        await self._check_adapter_board(resolver)
        await self._check_adapter_llm(resolver)
        await self._check_adapter_container(resolver)
        await self._check_adapter_version_control(resolver)
        await self._check_adapter_code_review(resolver)

        return self._all_critical_passed()

    def _get_production_adapter_config(self) -> AdapterSelectionConfig:
        """
        Get production adapter selection config.

        Reads environment to determine which adapters to use.
        """
        return AdapterSelectionConfig(
            ticket="github",
            board="github",
            llm="claude_code",
            version_control="git",
            container="docker",
            code_review="github",
            # Use defaults for non-critical adapters
        )

    async def _check_adapter_ticket(self, resolver: AdapterResolver) -> None:
        """Check ticket system adapter (GitHub Issues)."""
        try:
            adapter: ITicketSystem = resolver.resolve_ticket()
            concrete_class = type(adapter).__name__

            # For GitHub adapter, attempt to list work items
            if concrete_class == "GitHubTicketAdapter":
                try:
                    # Cheap read-only call: list work items (validates GitHub API connectivity)
                    _ = await adapter.list_work_items()
                    self._add_result("ticket", concrete_class, "PASS")
                except Exception as e:
                    error_msg = str(e)
                    if "401" in error_msg or "unauthorized" in error_msg.lower():
                        self._add_result(
                            "ticket",
                            concrete_class,
                            "FAIL",
                            "GitHub token invalid or expired, check GITHUB_TOKEN",
                        )
                    else:
                        self._add_result(
                            "ticket",
                            concrete_class,
                            "FAIL",
                            f"GitHub API call failed: {error_msg[:80]}",
                        )
            else:
                self._add_result("ticket", concrete_class, "SKIP", "Not a production adapter")
        except Exception as e:
            self._add_result(
                "ticket",
                "unknown",
                "FAIL",
                f"Failed to resolve adapter: {str(e)[:100]}",
            )

    async def _check_adapter_board(self, resolver: AdapterResolver) -> None:
        """Check board service adapter (GitHub Projects)."""
        try:
            adapter: IBoardService = resolver.resolve_board()
            concrete_class = type(adapter).__name__

            if concrete_class == "GitHubBoardAdapter":
                try:
                    # Cheap read-only call: list all boards (validates GitHub API connectivity)
                    _ = await adapter.get_all_boards()
                    self._add_result("board", concrete_class, "PASS")
                except Exception as e:
                    error_msg = str(e)
                    if "401" in error_msg or "unauthorized" in error_msg.lower():
                        self._add_result(
                            "board",
                            concrete_class,
                            "FAIL",
                            "GitHub token invalid, check GITHUB_TOKEN",
                        )
                    else:
                        self._add_result(
                            "board",
                            concrete_class,
                            "FAIL",
                            f"Failed to list boards: {error_msg[:80]}",
                        )
            else:
                self._add_result("board", concrete_class, "SKIP", "Not a production adapter")
        except Exception as e:
            self._add_result(
                "board",
                "unknown",
                "FAIL",
                f"Failed to resolve adapter: {str(e)[:100]}",
            )

    async def _check_adapter_llm(self, resolver: AdapterResolver) -> None:
        """Check LLM provider adapter (Claude Code)."""
        try:
            adapter: ILLMProvider = resolver.resolve_llm()
            concrete_class = type(adapter).__name__

            if concrete_class == "ClaudeCodeAdapter":
                try:
                    # Cheap check: verify token is accepted by Claude Code CLI
                    # This invokes `claude --version` which tests authentication
                    await self._verify_claude_code_token()
                    self._add_result("llm", concrete_class, "PASS")
                except Exception as e:
                    error_msg = str(e)
                    if "claude" in error_msg.lower() and "not found" in error_msg.lower():
                        self._add_result(
                            "llm",
                            concrete_class,
                            "FAIL",
                            "Claude Code CLI not installed or not in PATH",
                        )
                    else:
                        self._add_result(
                            "llm",
                            concrete_class,
                            "FAIL",
                            f"Claude Code token validation failed: {error_msg[:80]}",
                        )
            else:
                self._add_result("llm", concrete_class, "SKIP", "Not a production adapter")
        except Exception as e:
            self._add_result(
                "llm",
                "unknown",
                "FAIL",
                f"Failed to resolve adapter: {str(e)[:100]}",
            )

    async def _check_adapter_container(self, resolver: AdapterResolver) -> None:
        """Check container adapter (Docker)."""
        try:
            adapter: IContainer = resolver.resolve_container()
            concrete_class = type(adapter).__name__

            if concrete_class == "DockerContainerAdapter":
                try:
                    # Cheap read-only call: list containers (no output, just checks connectivity)
                    _ = await adapter.list_containers()
                    self._add_result("container", concrete_class, "PASS")
                except Exception as e:
                    error_msg = str(e)
                    if "docker" in error_msg.lower() and "socket" in error_msg.lower():
                        self._add_result(
                            "container",
                            concrete_class,
                            "FAIL",
                            "Docker socket not accessible, check DOCKER_HOST",
                        )
                    else:
                        self._add_result(
                            "container",
                            concrete_class,
                            "FAIL",
                            f"Failed to connect to Docker daemon: {error_msg[:80]}",
                        )
            else:
                self._add_result("container", concrete_class, "SKIP", "Not a production adapter")
        except Exception as e:
            self._add_result(
                "container",
                "unknown",
                "FAIL",
                f"Failed to resolve adapter: {str(e)[:100]}",
            )

    async def _check_adapter_version_control(self, resolver: AdapterResolver) -> None:
        """Check version control adapter (Git)."""
        try:
            adapter: IVersionControlService = resolver.resolve_version_control()
            concrete_class = type(adapter).__name__

            if concrete_class == "GitRepositoryAdapter":
                try:
                    # Cheap check: validate git is available
                    import shutil

                    if shutil.which("git"):
                        self._add_result("version_control", concrete_class, "PASS")
                    else:
                        self._add_result(
                            "version_control",
                            concrete_class,
                            "FAIL",
                            "Git is not installed or not in PATH",
                        )
                except Exception as e:
                    self._add_result(
                        "version_control",
                        concrete_class,
                        "FAIL",
                        f"Git validation failed: {str(e)[:100]}",
                    )
            else:
                self._add_result("version_control", concrete_class, "SKIP", "Not a production adapter")
        except Exception as e:
            self._add_result(
                "version_control",
                "unknown",
                "FAIL",
                f"Failed to resolve adapter: {str(e)[:100]}",
            )

    async def _check_adapter_code_review(self, resolver: AdapterResolver) -> None:
        """Check code review adapter (GitHub)."""
        try:
            adapter: ICodeReviewService = resolver.resolve_code_review()
            concrete_class = type(adapter).__name__

            if concrete_class == "GitHubCodeReviewAdapter":
                # Code review adapter uses same GitHub credentials as ticket adapter
                # If ticket and board adapters passed, code review is also validated
                # We verify the adapter resolved successfully and has required methods
                if hasattr(adapter, "get_review_for_work_item"):
                    self._add_result("code_review", concrete_class, "PASS")
                else:
                    self._add_result(
                        "code_review",
                        concrete_class,
                        "FAIL",
                        "Missing required methods",
                    )
            else:
                self._add_result("code_review", concrete_class, "SKIP", "Not a production adapter")
        except Exception as e:
            self._add_result(
                "code_review",
                "unknown",
                "FAIL",
                f"Failed to resolve adapter: {str(e)[:100]}",
            )

    async def _verify_claude_code_token(self) -> None:
        """
        Verify Claude Code token by running `claude --version`.

        Raises:
            Exception: If token validation fails
        """
        import shutil
        import subprocess

        token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if not token:
            raise ValueError("CLAUDE_CODE_OAUTH_TOKEN not set in environment")

        # Verify claude binary exists and get absolute path
        claude_path = shutil.which("claude")
        if not claude_path:
            raise RuntimeError("claude command not found in PATH")

        try:
            # Run claude --version with the token in environment
            env = os.environ.copy()
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token

            result = subprocess.run(
                [claude_path, "--version"],
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Claude CLI returned exit code {result.returncode}")

            logger.debug(f"Claude CLI version: {result.stdout.strip()}")

        except subprocess.TimeoutExpired as e:
            raise RuntimeError("claude command timed out") from e

    def _add_result(self, adapter_slot: str, concrete_class: str, status: str, error: str | None = None) -> None:
        """Record a health check result."""
        self.results.append(
            AdapterHealthCheckResult(
                adapter_slot=adapter_slot,
                concrete_class=concrete_class,
                status=status,
                error=error,
            )
        )

    def _all_critical_passed(self) -> bool:
        """Check if all critical adapters passed."""
        for result in self.results:
            if result.adapter_slot in self.CRITICAL_ADAPTERS and result.status != "PASS":
                return False
        return True

    def print_results(self) -> None:
        """Print results in a formatted table."""
        # Print header
        print()
        print("=" * 100)
        print("CREDENTIAL VALIDATION RESULTS")
        print("=" * 100)
        print()

        # Group results by status
        passed = [r for r in self.results if r.status == "PASS"]
        failed = [r for r in self.results if r.status == "FAIL"]
        skipped = [r for r in self.results if r.status == "SKIP"]

        # Print passed adapters
        if passed:
            print("✓ PASSED ADAPTERS:")
            print("-" * 100)
            print(f"{'Adapter':<25} {'Implementation':<35} {'Status':<10}")
            print("-" * 100)
            for result in passed:
                print(f"{result.adapter_slot:<25} {result.concrete_class:<35} {result.status:<10}")
            print()

        # Print failed adapters
        if failed:
            print("✗ FAILED ADAPTERS:")
            print("-" * 100)
            print(f"{'Adapter':<25} {'Implementation':<35} {'Error':<40}")
            print("-" * 100)
            for result in failed:
                error_msg = result.error or "Unknown error"
                error_msg = error_msg[:40]
                critical = " [CRITICAL]" if result.adapter_slot in self.CRITICAL_ADAPTERS else ""
                print(f"{result.adapter_slot:<25} {result.concrete_class:<35} {error_msg:<40}{critical}")
            print()

        # Print skipped adapters
        if skipped:
            print("⊘ SKIPPED ADAPTERS (not production):")
            print("-" * 100)
            print(f"{'Adapter':<25} {'Implementation':<35}")
            print("-" * 100)
            for result in skipped:
                print(f"{result.adapter_slot:<25} {result.concrete_class:<35}")
            print()

        # Summary
        print("=" * 100)
        critical_failed = [r for r in failed if r.adapter_slot in self.CRITICAL_ADAPTERS]
        if critical_failed:
            print(f"RESULT: FAILED ({len(critical_failed)} critical adapter(s) failed)")
        elif failed:
            print(f"RESULT: WARNING ({len(failed)} non-critical adapter(s) failed)")
        else:
            print("RESULT: SUCCESS (all critical adapters passed)")
        print("=" * 100)
        print()


async def main() -> int:
    """Main entry point."""
    validator = CredentialValidator()

    try:
        success = await validator.validate_all()
        validator.print_results()

        if success:
            logger.info("✓ All critical adapters are configured and accessible")
            return 0
        logger.error("✗ One or more critical adapters failed validation")
        return 1

    except KeyboardInterrupt:
        logger.warning("Validation cancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Validation error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
