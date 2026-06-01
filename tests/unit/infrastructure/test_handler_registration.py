"""CI gate test for event handler registration in production bootstrap.

This test discovers all EventHandler subclasses in application/event_handlers/
and verifies that each is explicitly registered in ProductionApplicationBootstrap.

This ensures no event handlers are accidentally left unwired when new handlers
are added to the system.
"""

import inspect
import re
from pathlib import Path

import pytest

from codetoreum.infrastructure.bootstrap.production_bootstrap import (
    ProductionApplicationBootstrap,
)
from codetoreum.infrastructure.event_bus import EventHandler


class TestHandlerRegistration:
    """Verify all event handlers are registered in production bootstrap."""

    @staticmethod
    def _discover_event_handlers() -> set[str]:
        """
        Discover all EventHandler subclasses in application/event_handlers/.

        Returns:
            Set of handler class names (e.g., {'WorkflowEventHandler', 'ExecutionEventHandler'})
        """
        event_handlers_dir = Path(__file__).parents[3] / "src" / "codetoreum" / "application" / "event_handlers"

        if not event_handlers_dir.exists():
            raise RuntimeError(f"Event handlers directory not found: {event_handlers_dir}")

        handlers = set()

        # Import all event handler modules
        for py_file in event_handlers_dir.glob("*.py"):
            if py_file.name.startswith("__"):
                continue

            # Import the module
            module_name = py_file.stem
            try:
                # Dynamically import the module
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    f"codetoreum.application.event_handlers.{module_name}", py_file
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Find all EventHandler subclasses in this module
                    for name, obj in inspect.getmembers(module):
                        if (
                            inspect.isclass(obj)
                            and issubclass(obj, EventHandler)
                            and obj is not EventHandler
                            and obj.__module__ == module.__name__
                        ):
                            handlers.add(name)
            except Exception as e:
                raise RuntimeError(f"Failed to import {module_name}: {e}") from e

        return handlers

    @staticmethod
    def _discover_registered_handlers() -> set[str]:
        """
        Discover all handler registrations in ProductionApplicationBootstrap.

        This searches for method calls to handler registration in the bootstrap
        and extracts the handler class names.

        Returns:
            Set of registered handler class names
        """
        bootstrap_file = (
            Path(__file__).parents[3]
            / "src"
            / "codetoreum"
            / "infrastructure"
            / "bootstrap"
            / "production_bootstrap.py"
        )

        if not bootstrap_file.exists():
            raise RuntimeError(f"Production bootstrap file not found: {bootstrap_file}")

        with open(bootstrap_file) as f:
            content = f.read()

        # Find all handler instantiations in the bootstrap file
        # Look for patterns like: handler = WorkflowEventHandler(...) or handler = ExecutionEventHandler(...)
        handlers = set()

        # Pattern 1: handler = ClassName(...)
        pattern = r"handler\s*=\s*(\w+Handler)\s*\("
        for match in re.finditer(pattern, content):
            handler_class = match.group(1)
            handlers.add(handler_class)

        # Pattern 2: pr_dispatch_handler = ClassName(...) or similar
        pattern = r"(\w+(?:_handler|_handlers))\s*=\s*(\w+Handler)\s*\("
        for match in re.finditer(pattern, content):
            handler_class = match.group(2)
            handlers.add(handler_class)

        return handlers

    def test_all_event_handlers_are_registered(self) -> None:
        """
        Verify that all discovered EventHandler subclasses are registered in ProductionApplicationBootstrap.

        This is a CI gate test to ensure new handlers are not accidentally left unwired.

        Raises:
            AssertionError: If any handler is discovered but not registered
        """
        discovered = self._discover_event_handlers()
        registered = self._discover_registered_handlers()

        # Filter out test/mock handlers - only check production handlers
        # Handlers like "MockSomeHandler" are allowed to be unregistered
        discovered_production = {h for h in discovered if not h.startswith("Mock")}

        unregistered = discovered_production - registered

        assert (
            not unregistered
        ), f"Found {len(unregistered)} event handler(s) not registered in ProductionApplicationBootstrap: {sorted(unregistered)}"

    def test_discovered_handlers_count(self) -> None:
        """Verify that we discover a reasonable number of handlers.

        This is a sanity check to ensure the discovery mechanism is working.
        """
        discovered = self._discover_event_handlers()
        assert len(discovered) > 0, "No event handlers discovered - discovery may be broken"

    def test_registered_handlers_count(self) -> None:
        """Verify that a reasonable number of handlers are registered.

        This is a sanity check to ensure the registration mechanism is working.
        """
        registered = self._discover_registered_handlers()
        assert len(registered) > 0, "No handlers registered - registration may be broken"
