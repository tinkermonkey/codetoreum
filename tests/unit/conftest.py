"""Common test fixtures and utilities for unit tests."""

import pytest

# Set default timeout for all unit tests to prevent hanging
pytestmark = pytest.mark.timeout(30)
