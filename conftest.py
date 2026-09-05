"""Root conftest.py for pytest configuration and shared fixtures."""

import pytest


# Add custom pytest configuration hooks
def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom settings."""
    config.addinivalue_line("markers", "unit: Unit tests for isolated components")
    config.addinivalue_line("markers", "integration: Integration tests with external dependencies")
    config.addinivalue_line("markers", "simulation: Full workflow simulation tests")
    config.addinivalue_line("markers", "slow: Tests that take significant time to run")
    config.addinivalue_line("markers", "contract: Contract tests for adapter implementations")
