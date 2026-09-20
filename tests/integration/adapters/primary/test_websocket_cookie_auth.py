"""
Regression tests for WebSocket authentication.

Covers the httpOnly-cookie auth fallback (`codetoreum_token`) added so
same-origin, Vite-proxied dashboard connections authenticate without a query
token, and the Origin allowlist check that guards it against cross-site
WebSocket hijacking (CSWSH).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from codetoreum.adapters.primary.websocket_adapter import WebSocketAdapter


class FakeAuthManager:
    """Minimal auth manager: a single token is valid."""

    def __init__(self, valid_token: str = "valid-token"):
        self.valid_token = valid_token
        self.validate_token_calls: list[str] = []

    def validate_token(self, token: str) -> bool:
        self.validate_token_calls.append(token)
        return token == self.valid_token


def make_mock_websocket(cookies: dict | None = None, origin: str | None = None) -> AsyncMock:
    ws = AsyncMock(spec=WebSocket)
    ws.cookies = cookies or {}
    ws.headers = {"origin": origin} if origin else {}
    ws.client = MagicMock(host="127.0.0.1")
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    # Disconnect immediately after the welcome message so the handler's
    # message loop exits deterministically instead of hanging.
    ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
    return ws


@pytest.mark.asyncio
async def test_query_token_auth_succeeds_without_cookie():
    auth_manager = FakeAuthManager()
    adapter = WebSocketAdapter(auth_manager=auth_manager)
    ws = make_mock_websocket()

    await adapter.handle_websocket(ws, token="valid-token")

    ws.accept.assert_awaited_once()
    ws.close.assert_not_called()


@pytest.mark.asyncio
async def test_missing_token_and_cookie_rejected():
    auth_manager = FakeAuthManager()
    adapter = WebSocketAdapter(auth_manager=auth_manager)
    ws = make_mock_websocket()

    await adapter.handle_websocket(ws, token=None)

    ws.close.assert_awaited_once_with(code=4001, reason="Unauthorized")
    ws.accept.assert_not_called()


@pytest.mark.asyncio
async def test_cookie_only_auth_succeeds_when_no_allowlist_configured():
    """No allowed_origins configured (e.g. dev) preserves prior permissive behavior."""
    auth_manager = FakeAuthManager()
    adapter = WebSocketAdapter(auth_manager=auth_manager, allowed_origins=None)
    ws = make_mock_websocket(cookies={"codetoreum_token": "valid-token"})

    await adapter.handle_websocket(ws, token=None)

    ws.accept.assert_awaited_once()
    ws.close.assert_not_called()
    assert auth_manager.validate_token_calls == ["valid-token"]


@pytest.mark.asyncio
async def test_query_token_takes_precedence_over_invalid_cookie():
    auth_manager = FakeAuthManager()
    adapter = WebSocketAdapter(auth_manager=auth_manager)
    ws = make_mock_websocket(cookies={"codetoreum_token": "garbage"})

    await adapter.handle_websocket(ws, token="valid-token")

    ws.accept.assert_awaited_once()
    ws.close.assert_not_called()
    assert auth_manager.validate_token_calls == ["valid-token"]


@pytest.mark.asyncio
async def test_cookie_auth_allowed_when_origin_matches_allowlist():
    auth_manager = FakeAuthManager()
    adapter = WebSocketAdapter(
        auth_manager=auth_manager,
        allowed_origins=["https://dashboard.example.com"],
    )
    ws = make_mock_websocket(
        cookies={"codetoreum_token": "valid-token"},
        origin="https://dashboard.example.com",
    )

    await adapter.handle_websocket(ws, token=None)

    ws.accept.assert_awaited_once()
    ws.close.assert_not_called()


@pytest.mark.asyncio
async def test_cookie_auth_rejected_when_origin_not_in_allowlist():
    """A cross-site page cannot ride a victim's valid cookie into a session (CSWSH)."""
    auth_manager = FakeAuthManager()
    adapter = WebSocketAdapter(
        auth_manager=auth_manager,
        allowed_origins=["https://dashboard.example.com"],
    )
    ws = make_mock_websocket(
        cookies={"codetoreum_token": "valid-token"},
        origin="https://evil.example.com",
    )

    await adapter.handle_websocket(ws, token=None)

    ws.close.assert_awaited_once_with(code=4001, reason="Unauthorized")
    ws.accept.assert_not_called()
    # Rejected on origin before the token is ever checked.
    assert auth_manager.validate_token_calls == []


@pytest.mark.asyncio
async def test_cookie_auth_allowed_when_allowlist_is_wildcard():
    auth_manager = FakeAuthManager()
    adapter = WebSocketAdapter(auth_manager=auth_manager, allowed_origins=["*"])
    ws = make_mock_websocket(
        cookies={"codetoreum_token": "valid-token"},
        origin="https://anywhere.example.com",
    )

    await adapter.handle_websocket(ws, token=None)

    ws.accept.assert_awaited_once()
    ws.close.assert_not_called()
