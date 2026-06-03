"""Tests for ExternalServiceError keyword-only construction."""

import pytest

from codetoreum.ports.exceptions import ExternalServiceError


class TestExternalServiceErrorKeywordOnly:
    """Test that ExternalServiceError requires keyword-only construction."""

    def test_keyword_construction_succeeds(self):
        """Test that keyword argument construction works."""
        error = ExternalServiceError(service="github", message="API failed")
        assert error.service == "github"
        assert "github error: API failed" in str(error)

    def test_positional_construction_raises_type_error(self):
        """Test that positional argument construction raises TypeError."""
        with pytest.raises(TypeError):
            ExternalServiceError("github", "API failed")

    def test_first_positional_argument_raises_type_error(self):
        """Test that passing only first positional argument raises TypeError."""
        with pytest.raises(TypeError):
            ExternalServiceError("github")

    def test_mixed_positional_and_keyword_raises_type_error(self):
        """Test that mixing positional and keyword arguments raises TypeError."""
        with pytest.raises(TypeError):
            ExternalServiceError("github", message="API failed")

    def test_missing_service_argument(self):
        """Test that missing service argument raises TypeError."""
        with pytest.raises(TypeError):
            ExternalServiceError(message="API failed")

    def test_missing_message_argument(self):
        """Test that missing message argument raises TypeError."""
        with pytest.raises(TypeError):
            ExternalServiceError(service="github")

    def test_service_attribute_set_correctly(self):
        """Test that service attribute is set from keyword argument."""
        error = ExternalServiceError(service="elastic", message="connection failed")
        assert error.service == "elastic"

    def test_error_message_format(self):
        """Test that error message is formatted correctly."""
        error = ExternalServiceError(service="docker", message="container not found")
        expected = "docker error: container not found"
        assert str(error) == expected

    def test_extra_keyword_arguments_raise_type_error(self):
        """Test that extra keyword arguments raise TypeError."""
        with pytest.raises(TypeError):
            ExternalServiceError(service="github", message="failed", extra="arg")
