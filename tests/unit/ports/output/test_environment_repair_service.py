"""Unit tests for environment repair service port interface.

Tests verify that the IEnvironmentRepairService interface cannot be
instantiated directly and follows the abstract base class pattern.
"""

import pytest

from codetoreum.ports.output.environment_repair_service import IEnvironmentRepairService

# ============================================================================
# IEnvironmentRepairService Interface Tests
# ============================================================================


class TestIEnvironmentRepairServiceInterface:
    """Test IEnvironmentRepairService port interface."""

    def test_interface_cannot_be_instantiated_directly(self):
        """Test that the interface cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IEnvironmentRepairService()

    def test_interface_is_abstract_base_class(self):
        """Test that IEnvironmentRepairService is an ABC."""
        from abc import ABC

        assert issubclass(IEnvironmentRepairService, ABC)

    def test_rebuild_environment_is_abstract_method(self):
        """Test that rebuild_environment is an abstract method."""
        assert hasattr(IEnvironmentRepairService, "rebuild_environment")
        assert getattr(IEnvironmentRepairService.rebuild_environment, "__isabstractmethod__", False)

    def test_verify_environment_is_abstract_method(self):
        """Test that verify_environment is an abstract method."""
        assert hasattr(IEnvironmentRepairService, "verify_environment")
        assert getattr(IEnvironmentRepairService.verify_environment, "__isabstractmethod__", False)

    def test_concrete_implementation_requires_both_methods(self):
        """Test that concrete implementations must implement both methods."""

        # Try to create a partial implementation
        class PartialImplementation(IEnvironmentRepairService):
            async def rebuild_environment(self, project, config, context):
                return None

        # Should raise TypeError because verify_environment is not implemented
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            PartialImplementation()

    def test_concrete_implementation_with_both_methods_succeeds(self):
        """Test that concrete implementations work with both methods."""

        class ConcreteImplementation(IEnvironmentRepairService):
            async def rebuild_environment(self, project, config, context):
                from codetoreum.domain.repair_cycle_types import RebuildResult

                return RebuildResult(
                    success=True,
                    duration_seconds=30.0,
                    actions_taken=(),
                    error=None,
                )

            async def verify_environment(self, project, config, context):
                from codetoreum.domain.repair_cycle_types import VerificationResult

                return VerificationResult(
                    healthy=True,
                    checks_passed=(),
                    checks_failed=(),
                    duration_seconds=5.0,
                )

        # This should succeed - no TypeError
        impl = ConcreteImplementation()
        assert impl is not None
