"""Common test fixtures and utilities for integration tests."""

import pytest

# Set default timeout for all integration tests to prevent hanging
pytestmark = pytest.mark.timeout(30)
