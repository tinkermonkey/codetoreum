"""Environment repair service port interface.

Defines the contract for rebuilding and verifying test environments during
the repair cycle. This interface separates environment-related operations
from the main repair cycle logic, allowing for independent implementations
and testing strategies.

The environment repair service handles:
1. Environment rebuild: Re-provisioning dependencies and configuration
2. Environment verification: Validating that the rebuilt environment is healthy

Both operations are critical for addressing environment-related test failures
(FailureClassification.ENVIRONMENT_ISSUE).
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from codetoreum.domain.repair_cycle_types import (
    RebuildResult,
    RepairTestRunConfig,
    VerificationResult,
)

if TYPE_CHECKING:
    from codetoreum.ports.output.repair_cycle_service import RepairCycleContext


class IEnvironmentRepairService(ABC):
    """Port interface for environment repair operations.

    Secondary port interface — implementations may delegate to specialized agents,
    container orchestration systems, or mock implementations for testing.

    Handles rebuilding and verification of test environments during the repair cycle,
    enabling automated recovery from environment-related test failures.
    """

    @abstractmethod
    async def rebuild_environment(
        self,
        project: str,
        config: RepairTestRunConfig,
        context: "RepairCycleContext",
    ) -> RebuildResult:
        """Rebuild the test environment after systemic fixes.

        Coordinates environment re-provisioning following systemic fixes,
        ensuring all dependencies are properly installed/updated and
        configuration is applied correctly.

        Args:
            project: Project identifier/name
            config: Test run configuration with timeout and other parameters
            context: Repair cycle execution context including work item,
                    workflow run, and iteration information

        Returns:
            RebuildResult with success status, actions taken, duration,
            and optional error message if rebuild failed

        Raises:
            TimeoutError: When rebuild exceeds the configured timeout
            Exception: For environment-specific errors (permission, disk space, etc.)
        """
        ...

    @abstractmethod
    async def verify_environment(
        self,
        project: str,
        config: RepairTestRunConfig,
        context: "RepairCycleContext",
    ) -> VerificationResult:
        """Verify that the rebuilt environment is ready for testing.

        Validates that the environment is properly configured, all required
        tools and dependencies are available, and the environment is
        in a healthy state ready for test execution.

        Args:
            project: Project identifier/name
            config: Test run configuration with timeout and other parameters
            context: Repair cycle execution context including work item,
                    workflow run, and iteration information

        Returns:
            VerificationResult with healthy status, passed/failed checks,
            and duration

        Raises:
            TimeoutError: When verification exceeds the configured timeout
            Exception: For environment-specific errors
        """
        ...
