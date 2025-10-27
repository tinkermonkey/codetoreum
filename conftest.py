"""Root conftest.py for pytest configuration and shared fixtures."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session.

    This fixture ensures all async tests use the same event loop.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def async_client() -> AsyncGenerator[None, None]:
    """Placeholder fixture for async HTTP client.

    This will be implemented when FastAPI app is added.
    """
    yield None


# Add custom pytest configuration hooks
def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom settings."""
    config.addinivalue_line("markers", "unit: Unit tests for isolated components")
    config.addinivalue_line(
        "markers", "integration: Integration tests with external dependencies"
    )
    config.addinivalue_line("markers", "simulation: Full workflow simulation tests")
    config.addinivalue_line("markers", "slow: Tests that take significant time to run")
    config.addinivalue_line(
        "markers", "contract: Contract tests for adapter implementations"
    )
