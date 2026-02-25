"""
Unit tests for error middleware security features.

Tests the security improvements:
- Production mode check disables debug regardless of env var
- Stack traces logged but never returned in API responses
- Sensitive data scrubbing
- Correlation ID tracking
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request, status
from pydantic import ValidationError as PydanticValidationError

from codetoreum.adapters.primary.error_middleware import (
    error_handling_middleware,
)


class TestProductionModeCheck:
    """Tests for production mode security checks."""

    @patch.dict(os.environ, {"CODETOREUM_ENV": "production", "CODETOREUM_DEBUG": "true"})
    def test_debug_mode_disabled_in_production(self):
        """Test that debug mode is always disabled in production."""
        # Re-import to pick up patched env vars
        import importlib

        from codetoreum.adapters.primary import error_middleware
        importlib.reload(error_middleware)

        # Debug mode should be False even though CODETOREUM_DEBUG=true
        assert error_middleware.IS_PRODUCTION is True
        assert error_middleware.DEBUG_MODE is False

    @patch.dict(os.environ, {"CODETOREUM_ENV": "development", "CODETOREUM_DEBUG": "true"})
    def test_debug_mode_enabled_in_development(self):
        """Test that debug mode can be enabled in development."""
        # Re-import to pick up patched env vars
        import importlib

        from codetoreum.adapters.primary import error_middleware
        importlib.reload(error_middleware)

        assert error_middleware.IS_PRODUCTION is False
        assert error_middleware.DEBUG_MODE is True

    @patch.dict(os.environ, {"CODETOREUM_ENV": "development", "CODETOREUM_DEBUG": "false"})
    def test_debug_mode_disabled_in_development_when_false(self):
        """Test that debug mode is off when explicitly set to false."""
        # Re-import to pick up patched env vars
        import importlib

        from codetoreum.adapters.primary import error_middleware
        importlib.reload(error_middleware)

        assert error_middleware.IS_PRODUCTION is False
        assert error_middleware.DEBUG_MODE is False


class TestErrorMiddlewareCorrelationId:
    """Tests for correlation ID functionality."""

    @pytest.mark.asyncio
    async def test_correlation_id_generated(self):
        """Test that correlation ID is generated for each request."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.method = "GET"
        request.url.path = "/test"
        # Mock headers.get() to return None so a UUID is generated
        request.headers.get = MagicMock(return_value=None)

        async def call_next(req):
            response = MagicMock()
            response.headers = {}
            return response

        await error_handling_middleware(request, call_next)

        assert hasattr(request.state, "correlation_id")
        assert request.state.correlation_id is not None
        assert len(request.state.correlation_id) > 0

    @pytest.mark.asyncio
    async def test_correlation_id_unique_per_request(self):
        """Test that each request gets a unique correlation ID."""
        request1 = MagicMock(spec=Request)
        request1.state = MagicMock()
        request1.method = "GET"
        request1.url.path = "/test1"
        request1.headers.get = MagicMock(return_value=None)

        request2 = MagicMock(spec=Request)
        request2.state = MagicMock()
        request2.method = "GET"
        request2.url.path = "/test2"
        request2.headers.get = MagicMock(return_value=None)

        async def call_next(req):
            response = MagicMock()
            response.headers = {}
            return response

        await error_handling_middleware(request1, call_next)
        await error_handling_middleware(request2, call_next)

        assert request1.state.correlation_id != request2.state.correlation_id


class TestErrorMiddlewareStackTraces:
    """Tests for stack trace handling security."""

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"CODETOREUM_ENV": "production"})
    async def test_stack_traces_not_returned_in_production(self):
        """Test that stack traces are never returned in production API responses."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.method = "GET"
        request.url.path = "/test"
        request.headers.get = MagicMock(return_value=None)

        async def call_next(req):
            raise Exception("Internal error with sensitive data: api_key=secret123")

        # Re-import to pick up patched env vars
        import importlib

        from codetoreum.adapters.primary import error_middleware
        importlib.reload(error_middleware)

        response = await error_middleware.error_handling_middleware(request, call_next)

        # Check response doesn't contain stack trace or sensitive data
        response_data = response.body.decode()
        assert "Traceback" not in response_data
        assert "secret123" not in response_data
        assert "api_key" not in response_data
        assert "correlation_id" in response_data

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"CODETOREUM_ENV": "development", "CODETOREUM_DEBUG": "true"})
    async def test_stack_traces_logged_in_development(self):
        """Test that stack traces are logged even in development."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.method = "GET"
        request.url.path = "/test"
        request.headers.get = MagicMock(return_value=None)

        test_exception = Exception("Test error")

        async def call_next(req):
            raise test_exception

        # Re-import to pick up patched env vars
        import importlib

        from codetoreum.adapters.primary import error_middleware
        importlib.reload(error_middleware)

        # Patch the logger after reload
        with patch.object(error_middleware, "logger") as mock_logger:
            await error_middleware.error_handling_middleware(request, call_next)

            # Verify that logger.error was called with exc_info=True
            mock_logger.error.assert_called_once()
            call_kwargs = mock_logger.error.call_args[1]
            assert call_kwargs.get("exc_info") is True

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"CODETOREUM_ENV": "development", "CODETOREUM_DEBUG": "true"})
    async def test_debug_mode_returns_error_type_but_not_stack_trace(self):
        """Test that debug mode returns error type and message but not full stack trace."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.method = "GET"
        request.url.path = "/test"
        request.headers.get = MagicMock(return_value=None)

        async def call_next(req):
            raise ValueError("Test validation error")

        # Re-import to pick up patched env vars
        import importlib

        from codetoreum.adapters.primary import error_middleware
        importlib.reload(error_middleware)

        response = await error_middleware.error_handling_middleware(request, call_next)

        response_data = response.body.decode()

        # Should include error message in debug mode
        assert "Test validation error" in response_data
        # But should NOT include stack trace
        assert "Traceback" not in response_data
        assert "File " not in response_data  # Stack trace line format


class TestErrorMiddlewareLogging:
    """Tests for proper logging in error middleware."""

    @pytest.mark.asyncio
    @patch("codetoreum.adapters.primary.error_middleware.logger")
    async def test_validation_errors_logged(self, mock_logger):
        """Test that validation errors are logged."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.method = "POST"
        request.url.path = "/api/test"
        request.headers.get = MagicMock(return_value=None)

        # Use Pydantic V2 error type format with InitErrorDetails required keys
        validation_error = PydanticValidationError.from_exception_data(
            "ValidationError",
            [{"loc": ("body", "field"), "type": "missing", "input": {}, "ctx": {}}]
        )

        async def call_next(req):
            raise validation_error

        await error_handling_middleware(request, call_next)

        # Verify logging was called
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        assert "Validation error" in call_args[0]
        assert "/api/test" in call_args[0]

    @pytest.mark.asyncio
    @patch("codetoreum.adapters.primary.error_middleware.logger")
    async def test_permission_errors_logged_as_warning(self, mock_logger):
        """Test that permission errors are logged as warnings."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.method = "GET"
        request.url.path = "/api/protected"
        request.headers.get = MagicMock(return_value=None)

        async def call_next(req):
            raise PermissionError("Access denied")

        await error_handling_middleware(request, call_next)

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0]
        assert "Permission denied" in call_args[0]
        assert "/api/protected" in call_args[0]

    @pytest.mark.asyncio
    @patch("codetoreum.adapters.primary.error_middleware.logger")
    async def test_unhandled_errors_logged_as_error(self, mock_logger):
        """Test that unhandled exceptions are logged as errors."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.method = "GET"
        request.url.path = "/api/test"
        request.headers.get = MagicMock(return_value=None)

        async def call_next(req):
            raise RuntimeError("Unexpected error")

        await error_handling_middleware(request, call_next)

        # Verify error was logged with full traceback
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args[0]
        assert "Unhandled exception" in call_args[0]
        assert "RuntimeError" in call_args[0]

        # Verify exc_info=True was passed to capture stack trace
        call_kwargs = mock_logger.error.call_args[1]
        assert call_kwargs.get("exc_info") is True


class TestErrorMiddlewareResponseFormat:
    """Tests for error response format."""

    @pytest.mark.asyncio
    async def test_error_response_includes_correlation_id(self):
        """Test that all error responses include correlation ID."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.method = "GET"
        request.url.path = "/test"
        request.headers.get = MagicMock(return_value=None)

        async def call_next(req):
            raise ValueError("Test error")

        response = await error_handling_middleware(request, call_next)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response_data = response.body.decode()
        assert "correlation_id" in response_data

    @pytest.mark.asyncio
    async def test_error_response_includes_path(self):
        """Test that error responses include the request path."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.method = "POST"
        request.url.path = "/api/test/endpoint"
        request.headers.get = MagicMock(return_value=None)

        async def call_next(req):
            raise ValueError("Test error")

        response = await error_handling_middleware(request, call_next)

        response_data = response.body.decode()
        assert "/api/test/endpoint" in response_data

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"CODETOREUM_ENV": "production"})
    async def test_production_error_response_generic(self):
        """Test that production returns generic error messages."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.method = "GET"
        request.url.path = "/test"
        request.headers.get = MagicMock(return_value=None)

        async def call_next(req):
            raise RuntimeError("Internal error with DB connection string: postgresql://user:pass@host/db")

        # Re-import to pick up patched env vars
        import importlib

        from codetoreum.adapters.primary import error_middleware
        importlib.reload(error_middleware)

        response = await error_middleware.error_handling_middleware(request, call_next)

        response_data = response.body.decode()

        # Should have generic message
        assert "unexpected error occurred" in response_data.lower()
        # Should NOT include sensitive details
        assert "postgresql://" not in response_data
        assert "user:pass" not in response_data
        # Should include support reference
        assert "support" in response_data.lower()
        assert "correlation" in response_data.lower()
