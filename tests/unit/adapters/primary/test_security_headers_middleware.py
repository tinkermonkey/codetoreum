"""
Unit tests for security headers middleware.

Tests verify that security headers are correctly applied including:
- CSP header allows WebSocket connections (ws: and wss:)
- Other security headers are set correctly
- HSTS header is conditionally applied based on HTTPS configuration
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from codetoreum.adapters.primary.middleware.security import (
    security_headers_middleware,
)


class TestSecurityHeadersGeneral:
    """Tests for general security headers."""

    @pytest.mark.asyncio
    async def test_x_content_type_options_header(self):
        """Test that X-Content-Type-Options header prevents MIME type sniffing."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)

        assert result.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_x_frame_options_header(self):
        """Test that X-Frame-Options header prevents clickjacking."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)

        assert result.headers["X-Frame-Options"] == "DENY"

    @pytest.mark.asyncio
    async def test_x_xss_protection_header(self):
        """Test that X-XSS-Protection header enables XSS filtering."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)

        assert result.headers["X-XSS-Protection"] == "1; mode=block"


class TestHSTSHeader:
    """Tests for HSTS (HTTP Strict Transport Security) header."""

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"API_USE_HTTPS": "true"})
    async def test_hsts_header_when_https_enabled(self):
        """Test that HSTS header is set when HTTPS is enabled."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)

        assert "Strict-Transport-Security" in result.headers
        assert "max-age=31536000" in result.headers["Strict-Transport-Security"]
        assert "includeSubDomains" in result.headers["Strict-Transport-Security"]

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"API_USE_HTTPS": "false"})
    async def test_hsts_header_not_set_when_https_disabled(self):
        """Test that HSTS header is not set when HTTPS is disabled."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)

        assert "Strict-Transport-Security" not in result.headers

    @pytest.mark.asyncio
    async def test_hsts_header_not_set_by_default(self):
        """Test that HSTS header is not set by default (when env var not set)."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        # Ensure API_USE_HTTPS is not set
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("API_USE_HTTPS", None)
            result = await security_headers_middleware(request, call_next)

        assert "Strict-Transport-Security" not in result.headers


class TestContentSecurityPolicy:
    """Tests for Content Security Policy header."""

    @pytest.mark.asyncio
    async def test_csp_header_present(self):
        """Test that CSP header is set."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)

        assert "Content-Security-Policy" in result.headers

    @pytest.mark.asyncio
    async def test_csp_default_src_self(self):
        """Test that CSP default-src is set to 'self'."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)
        csp = result.headers["Content-Security-Policy"]

        assert "default-src 'self'" in csp

    @pytest.mark.asyncio
    async def test_csp_script_src_self_and_unsafe_inline(self):
        """Test that CSP script-src allows 'self' and 'unsafe-inline'."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)
        csp = result.headers["Content-Security-Policy"]

        assert "script-src 'self' 'unsafe-inline'" in csp

    @pytest.mark.asyncio
    async def test_csp_style_src_self_and_unsafe_inline(self):
        """Test that CSP style-src allows 'self' and 'unsafe-inline'."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)
        csp = result.headers["Content-Security-Policy"]

        assert "style-src 'self' 'unsafe-inline'" in csp

    @pytest.mark.asyncio
    async def test_csp_img_src_self_and_data(self):
        """Test that CSP img-src allows 'self' and data: URLs."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)
        csp = result.headers["Content-Security-Policy"]

        assert "img-src 'self' data:" in csp

    @pytest.mark.asyncio
    async def test_csp_font_src_self(self):
        """Test that CSP font-src is set to 'self'."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)
        csp = result.headers["Content-Security-Policy"]

        assert "font-src 'self'" in csp


class TestWebSocketConnectivity:
    """Tests for WebSocket CSP directives."""

    @pytest.mark.asyncio
    async def test_csp_connect_src_includes_ws_scheme(self):
        """Test that CSP connect-src includes ws: for WebSocket support."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)
        csp = result.headers["Content-Security-Policy"]

        assert "connect-src 'self' ws: wss:" in csp

    @pytest.mark.asyncio
    async def test_csp_connect_src_includes_self(self):
        """Test that CSP connect-src includes 'self' for same-origin requests."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)
        csp = result.headers["Content-Security-Policy"]

        assert "'self'" in csp.split("connect-src")[1].split(";")[0]

    @pytest.mark.asyncio
    async def test_csp_connect_src_includes_secure_ws_scheme(self):
        """Test that CSP connect-src includes wss: for secure WebSocket support."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)
        csp = result.headers["Content-Security-Policy"]

        assert "wss:" in csp


class TestMiddlewareChaining:
    """Tests for middleware execution and chaining."""

    @pytest.mark.asyncio
    async def test_middleware_calls_next_handler(self):
        """Test that middleware correctly calls the next handler."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        result = await security_headers_middleware(request, call_next)

        call_next.assert_called_once_with(request)
        assert result is response

    @pytest.mark.asyncio
    async def test_middleware_preserves_response_body(self):
        """Test that middleware preserves the response body."""
        request = MagicMock(spec=Request)
        response = MagicMock()
        response.headers = {}
        response.status_code = 200
        response.body = b"test response"

        async def call_next(req):
            return response

        result = await security_headers_middleware(request, call_next)

        assert result.body == b"test response"
        assert result.status_code == 200
