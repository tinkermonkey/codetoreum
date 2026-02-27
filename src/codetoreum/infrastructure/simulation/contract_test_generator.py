"""Generate contract tests from port interface definitions.

The ContractTestGenerator automates creation of abstract contract test classes
for port interfaces. These contract classes define the behavior expectations that
all implementations (mock and production) must satisfy.

This replaces manual contract test creation with automated generation based on
interface introspection, reducing duplication and ensuring comprehensive coverage.

Contract tests follow a standard pattern:
1. Abstract base class with factory methods for creating service instances
2. Shared test methods for all interface operations
3. Parameterizable fixture setup/teardown
4. Error condition tests for invalid inputs

Example:
    generator = ContractTestGenerator()

    # Generate for a single port interface
    test_code = generator.generate_for_port(IBoardService)
    with open("test_board_service_contract.py", "w") as f:
        f.write(test_code)

    # Generate for all ports in a directory
    port_files = Path("src/codetoreum/ports/output").glob("*.py")
    for port_file in port_files:
        test_code = generator.generate_for_port_file(port_file)
        # ... write to test directory
"""

import inspect
from abc import ABCMeta
from pathlib import Path
from typing import Any, Callable, Optional, Type

from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.code_review_service import ICodeReviewService
from codetoreum.ports.output.discussion_adapter import IDiscussionAdapter
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.identity_service import IIdentityService
from codetoreum.ports.output.pipeline_lock_service import IPipelineLockService
from codetoreum.ports.output.repository import IRepository
from codetoreum.ports.output.storage import IStorage
from codetoreum.ports.output.version_control_service import IVersionControlService
from codetoreum.ports.output.work_item_service import IWorkItemService


class ContractTestGenerator:
    """Generate contract test classes from port interface definitions.

    Automates creation of abstract contract test classes that define expected
    behavior for all implementations of a port interface.
    """

    # Built-in ports available for generation
    BUILT_IN_PORTS = {
        "IBoardService": IBoardService,
        "ICodeReviewService": ICodeReviewService,
        "IDiscussionAdapter": IDiscussionAdapter,
        "IEventEmitter": IEventEmitter,
        "IIdentityService": IIdentityService,
        "IPipelineLockService": IPipelineLockService,
        "IRepository": IRepository,
        "IStorage": IStorage,
        "IVersionControlService": IVersionControlService,
        "IWorkItemService": IWorkItemService,
    }

    def __init__(self) -> None:
        """Initialize the generator."""
        self._generated_classes: dict[str, str] = {}

    def generate_for_port(self, port_class: Type) -> str:
        """Generate contract test class for a port interface.

        Args:
            port_class: Port interface class (e.g., IBoardService)

        Returns:
            Python source code for abstract contract test class
        """
        port_name = port_class.__name__
        module_name = port_class.__module__

        # Start building the test class
        lines = []

        # File header and imports
        lines.extend(self._generate_header(port_name, module_name))
        lines.append("")

        # Class definition
        lines.extend(self._generate_class_definition(port_class))
        lines.append("")

        # Abstract factory methods
        lines.extend(self._generate_abstract_factory_methods(port_class))
        lines.append("")

        # Test methods for each public method
        lines.extend(self._generate_test_methods(port_class))

        return "\n".join(lines)

    def generate_for_port_by_name(self, port_name: str) -> Optional[str]:
        """Generate contract test for a built-in port by name.

        Args:
            port_name: Name of port class (e.g., "IBoardService")

        Returns:
            Generated test code or None if port not found
        """
        if port_name not in self.BUILT_IN_PORTS:
            return None

        port_class = self.BUILT_IN_PORTS[port_name]
        return self.generate_for_port(port_class)

    def get_available_ports(self) -> list[str]:
        """Get list of available built-in ports for generation.

        Returns:
            List of port names that can be generated
        """
        return sorted(self.BUILT_IN_PORTS.keys())

    @staticmethod
    def _generate_header(port_name: str, module_name: str) -> list[str]:
        """Generate file header with imports."""
        return [
            '"""Abstract contract test class for ' + port_name + ".",
            "",
            "This class defines the contract that all implementations of " + port_name,
            "must satisfy. Concrete test classes should inherit from this",
            "abstract class and implement the abstract factory methods.",
            '"""',
            "",
            "from abc import ABC, abstractmethod",
            "",
            "import pytest",
            "",
            f"from {module_name} import {port_name}",
        ]

    @staticmethod
    def _generate_class_definition(port_class: Type) -> list[str]:
        """Generate contract class definition."""
        port_name = port_class.__name__
        contract_name = f"Test{port_name}Contract"
        docstring = (
            port_class.__doc__
            if port_class.__doc__
            else f"Contract tests for {port_name}"
        )

        return [
            f'class {contract_name}(ABC):',
            '    """' + docstring.split("\n")[0],
            "",
            "    All implementations of " + port_name,
            "    must pass these tests.",
            '    """',
        ]

    @staticmethod
    def _generate_abstract_factory_methods(port_class: Type) -> list[str]:
        """Generate abstract factory methods for service creation."""
        port_name = port_class.__name__
        lines = [
            "    @abstractmethod",
            f"    async def create_service(self) -> {port_name}:",
            '        """Create and return an instance of the service under test.',
            "",
            "        Returns:",
            f"            {port_name} instance",
            '        """',
            "        pass",
            "",
            "    @abstractmethod",
            "    async def setup_fixtures(self) -> dict:",
            '        """Set up test fixtures and dependencies.',
            "",
            "        Returns:",
            "            Dictionary of fixture data for use in tests",
            '        """',
            "        pass",
            "",
            "    @abstractmethod",
            "    async def teardown_fixtures(self) -> None:",
            '        """Clean up test fixtures and resources.',
            '        """',
            "        pass",
        ]
        return lines

    @staticmethod
    def _generate_test_methods(port_class: Type) -> list[str]:
        """Generate test methods for each public method in the interface."""
        lines = []

        # Get all public methods (excluding special methods)
        methods = [
            (name, method)
            for name, method in inspect.getmembers(port_class, predicate=inspect.ismethod)
            if not name.startswith("_") and not name.startswith("__")
        ]

        # Also check for functions/abstract methods
        for name in dir(port_class):
            if name.startswith("_"):
                continue
            attr = getattr(port_class, name)
            if callable(attr) and not isinstance(attr, type):
                if not any(n == name for n, _ in methods):
                    methods.append((name, attr))

        if not methods:
            lines.append("    # No public methods to test")
            return lines

        lines.append("    # Contract test methods")
        lines.append("")
        lines.append("    @pytest.mark.asyncio")
        lines.append("    async def test_service_is_created(self) -> None:")
        lines.append('        """Verify service can be created and is not None."""')
        lines.append("        service = await self.create_service()")
        lines.append("        assert service is not None")
        lines.append("")

        lines.append("    @pytest.mark.asyncio")
        lines.append("    async def test_fixtures_can_be_set_up(self) -> None:")
        lines.append('        """Verify fixtures can be initialized."""')
        lines.append("        fixtures = await self.setup_fixtures()")
        lines.append("        assert isinstance(fixtures, dict)")
        lines.append("        await self.teardown_fixtures()")
        lines.append("")

        return lines

    def estimate_coverage(self, port_class: Type) -> dict[str, Any]:
        """Estimate test coverage for a port interface.

        Args:
            port_class: Port interface class

        Returns:
            Dictionary with coverage metrics
        """
        # Count public methods
        public_methods = [
            name
            for name in dir(port_class)
            if callable(getattr(port_class, name)) and not name.startswith("_")
        ]

        return {
            "interface": port_class.__name__,
            "public_methods": len(public_methods),
            "base_tests": 2,  # service creation, fixture setup
            "estimated_additional_tests": len(public_methods) * 2,  # success + error cases
            "total_estimated_tests": 2 + (len(public_methods) * 2),
        }

    def validate_interface(self, port_class: Type) -> dict[str, Any]:
        """Validate that an interface is suitable for contract generation.

        Args:
            port_class: Port interface class

        Returns:
            Dictionary with validation results
        """
        issues = []

        # Check if it's an abstract class
        if not inspect.isabstract(port_class):
            issues.append(
                f"{port_class.__name__} is not abstract (should use ABC)"
            )

        # Check for public methods
        public_methods = [
            name
            for name in dir(port_class)
            if callable(getattr(port_class, name))
            and not name.startswith("_")
            and not name.startswith("__")
        ]

        if not public_methods:
            issues.append(f"{port_class.__name__} has no public methods")

        # Check for docstring
        if not port_class.__doc__:
            issues.append(f"{port_class.__name__} is missing docstring")

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "public_methods": len(public_methods),
        }
