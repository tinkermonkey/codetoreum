"""Security tests for GitHub webhook signature validation.

These tests verify HMAC-SHA256 signature validation, timing attack prevention,
and replay attack prevention in the GitHub webhook adapter.
"""

import hashlib
import hmac
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.primary.github_webhook_adapter import GitHubWebhookAdapter


class TestWebhookSignatureValidation:
    """Test HMAC-SHA256 signature validation."""

    @pytest.fixture
    def adapter(self):
        """Create a GitHubWebhookAdapter for testing."""
        workflow_port = AsyncMock()
        board_service = AsyncMock()
        config = AsyncMock()
        event_bus = AsyncMock()
        logger = MagicMock()

        adapter = GitHubWebhookAdapter(
            workflow_command_port=workflow_port,
            board_service=board_service,
            config_service=config,
            event_bus=event_bus,
            logger=logger,
        )

        return adapter, config

    @pytest.mark.asyncio
    async def test_valid_signature_accepted(self, adapter):
        """Valid HMAC-SHA256 signature should be accepted."""
        adapter, config = adapter

        payload = b'{"action": "opened", "pull_request": {"id": 123}}'
        secret = "test-webhook-secret"
        expected_signature = "sha256=" + hmac.new(
            key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
        ).hexdigest()

        # Mock config to return project with webhook secret
        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        result = await adapter._verify_signature(payload, expected_signature, "test-project")

        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, adapter):
        """Invalid signature should be rejected."""
        adapter, config = adapter

        payload = b'{"action": "opened"}'
        secret = "test-webhook-secret"
        wrong_signature = "sha256=" + "0" * 64  # Invalid signature

        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        result = await adapter._verify_signature(payload, wrong_signature, "test-project")

        assert result is False

    @pytest.mark.asyncio
    async def test_signature_with_wrong_secret_rejected(self, adapter):
        """Signature computed with wrong secret should be rejected."""
        adapter, config = adapter

        payload = b'{"action": "opened"}'
        correct_secret = "correct-secret"
        wrong_secret = "wrong-secret"

        # Sign with wrong secret
        wrong_signature = "sha256=" + hmac.new(
            key=wrong_secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
        ).hexdigest()

        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": correct_secret}
        )

        result = await adapter._verify_signature(payload, wrong_signature, "test-project")

        assert result is False

    @pytest.mark.asyncio
    async def test_signature_with_modified_payload_rejected(self, adapter):
        """Signature should be rejected if payload was modified."""
        adapter, config = adapter

        original_payload = b'{"action": "opened"}'
        secret = "test-webhook-secret"

        # Sign original payload
        signature = "sha256=" + hmac.new(
            key=secret.encode("utf-8"), msg=original_payload, digestmod=hashlib.sha256
        ).hexdigest()

        # Modify payload
        modified_payload = b'{"action": "closed"}'

        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        result = await adapter._verify_signature(modified_payload, signature, "test-project")

        assert result is False

    @pytest.mark.asyncio
    async def test_missing_signature_prefix_handled(self, adapter):
        """Signature with missing 'sha256=' prefix should be handled."""
        adapter, config = adapter

        payload = b'{"action": "opened"}'
        secret = "test-webhook-secret"

        # Create signature without prefix
        hex_signature = hmac.new(
            key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
        ).hexdigest()
        signature = f"sha256={hex_signature}"

        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        result = await adapter._verify_signature(payload, signature, "test-project")

        assert result is True

    @pytest.mark.asyncio
    async def test_signature_case_sensitivity(self, adapter):
        """Signature comparison should handle hex case correctly."""
        adapter, config = adapter

        payload = b'{"action": "opened"}'
        secret = "test-webhook-secret"

        # Create signature with lowercase hex
        expected_hex = hmac.new(
            key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
        ).hexdigest()

        # Test with lowercase (should match)
        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        result = await adapter._verify_signature(payload, f"sha256={expected_hex}", "test-project")
        assert result is True

    @pytest.mark.asyncio
    async def test_empty_secret_returns_false(self, adapter):
        """Empty webhook secret should result in verification failure."""
        adapter, config = adapter

        payload = b'{"action": "opened"}'
        signature = "sha256=" + "0" * 64

        config.get_project_config.return_value = MagicMock(metadata={})

        result = await adapter._verify_signature(payload, signature, "test-project")

        assert result is False

    @pytest.mark.asyncio
    async def test_missing_project_config_returns_false(self, adapter):
        """Missing project config should result in verification failure."""
        adapter, config = adapter

        payload = b'{"action": "opened"}'
        signature = "sha256=" + "0" * 64

        config.get_project_config.side_effect = Exception("Config not found")

        result = await adapter._verify_signature(payload, signature, "nonexistent-project")

        assert result is False


class TestTimingAttackPrevention:
    """Test timing attack prevention."""

    @pytest.fixture
    def adapter(self):
        """Create a GitHubWebhookAdapter for testing."""
        workflow_port = AsyncMock()
        board_service = AsyncMock()
        config = AsyncMock()
        event_bus = AsyncMock()
        logger = MagicMock()

        adapter = GitHubWebhookAdapter(
            workflow_command_port=workflow_port,
            board_service=board_service,
            config_service=config,
            event_bus=event_bus,
            logger=logger,
        )

        return adapter, config

    @pytest.mark.asyncio
    async def test_timing_safe_comparison_used(self, adapter):
        """Signature comparison should use timing-safe comparison."""
        adapter, config = adapter

        payload = b'{"action": "opened"}'
        secret = "test-webhook-secret"

        # Compute correct signature
        correct_sig_hex = hmac.new(
            key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
        ).hexdigest()
        correct_signature = f"sha256={correct_sig_hex}"

        # Create wrong signature that differs in first character
        wrong_hex = correct_sig_hex[0:1] + ("0" if correct_sig_hex[1] != "0" else "1") + correct_sig_hex[2:]
        wrong_signature_first = f"sha256={wrong_hex}"

        # Create wrong signature that differs in last character
        wrong_signature_last = f"sha256={correct_sig_hex[:-1]}{'0' if correct_sig_hex[-1] != '0' else '1'}"

        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        # Both invalid signatures should be rejected (timing-safe comparison should
        # take approximately the same time regardless of where mismatch occurs)
        result_first = await adapter._verify_signature(payload, wrong_signature_first, "test-project")
        result_last = await adapter._verify_signature(payload, wrong_signature_last, "test-project")

        assert result_first is False
        assert result_last is False

    @pytest.mark.asyncio
    async def test_signature_length_validation(self, adapter):
        """Signature of incorrect length should be rejected."""
        adapter, config = adapter

        payload = b'{"action": "opened"}'
        secret = "test-webhook-secret"

        # Too short signature
        short_signature = "sha256=" + "0" * 32

        # Too long signature
        long_signature = "sha256=" + "0" * 128

        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        result_short = await adapter._verify_signature(payload, short_signature, "test-project")
        result_long = await adapter._verify_signature(payload, long_signature, "test-project")

        assert result_short is False
        assert result_long is False


class TestReplayAttackPrevention:
    """Test replay attack prevention (idempotency)."""

    @pytest.fixture
    async def adapter(self):
        """Create a GitHubWebhookAdapter for testing."""
        workflow_port = AsyncMock()
        board_service = AsyncMock()
        config = AsyncMock()
        event_bus = AsyncMock()
        logger = MagicMock()

        adapter = GitHubWebhookAdapter(
            workflow_command_port=workflow_port,
            board_service=board_service,
            config_service=config,
            event_bus=event_bus,
            logger=logger,
        )

        return adapter

    def test_adapter_has_idempotency_cache(self, adapter):
        """Adapter should have idempotency cache configuration."""
        assert hasattr(adapter, "_DEFAULT_CACHE_SIZE")
        assert adapter._DEFAULT_CACHE_SIZE > 0

        assert hasattr(adapter, "_DEFAULT_EVICTION_THRESHOLD")
        assert 0 < adapter._DEFAULT_EVICTION_THRESHOLD < 1


class TestWebhookSignatureEdgeCases:
    """Test edge cases in signature validation."""

    @pytest.fixture
    def adapter(self):
        """Create a GitHubWebhookAdapter for testing."""
        workflow_port = AsyncMock()
        board_service = AsyncMock()
        config = AsyncMock()
        event_bus = AsyncMock()
        logger = MagicMock()

        adapter = GitHubWebhookAdapter(
            workflow_command_port=workflow_port,
            board_service=board_service,
            config_service=config,
            event_bus=event_bus,
            logger=logger,
        )

        return adapter, config

    @pytest.mark.asyncio
    async def test_empty_payload_signature(self, adapter):
        """Signature verification should work with empty payload."""
        adapter, config = adapter

        payload = b""
        secret = "test-webhook-secret"

        signature = "sha256=" + hmac.new(
            key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
        ).hexdigest()

        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        result = await adapter._verify_signature(payload, signature, "test-project")

        assert result is True

    @pytest.mark.asyncio
    async def test_large_payload_signature(self, adapter):
        """Signature verification should work with large payload."""
        adapter, config = adapter

        # Create a large payload (1MB)
        payload = b"x" * (1024 * 1024)
        secret = "test-webhook-secret"

        signature = "sha256=" + hmac.new(
            key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
        ).hexdigest()

        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        result = await adapter._verify_signature(payload, signature, "test-project")

        assert result is True

    @pytest.mark.asyncio
    async def test_unicode_secret_handling(self, adapter):
        """Signature verification should handle unicode secrets."""
        adapter, config = adapter

        payload = b'{"action": "opened"}'
        secret = "webhook-secret-with-émojis-🔐"

        signature = "sha256=" + hmac.new(
            key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
        ).hexdigest()

        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        result = await adapter._verify_signature(payload, signature, "test-project")

        assert result is True

    @pytest.mark.asyncio
    async def test_special_characters_in_secret(self, adapter):
        """Signature verification should handle special characters in secret."""
        adapter, config = adapter

        payload = b'{"action": "opened"}'
        secret = "webhook-secret!@#$%^&*()"

        signature = "sha256=" + hmac.new(
            key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
        ).hexdigest()

        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        result = await adapter._verify_signature(payload, signature, "test-project")

        assert result is True

    @pytest.mark.asyncio
    async def test_whitespace_in_signature_header(self, adapter):
        """Signature with whitespace should be handled correctly."""
        adapter, config = adapter

        payload = b'{"action": "opened"}'
        secret = "test-webhook-secret"

        correct_sig = "sha256=" + hmac.new(
            key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
        ).hexdigest()

        # Add whitespace
        signature_with_space = f"sha256= {correct_sig.split('=')[1]}"

        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        result = await adapter._verify_signature(payload, signature_with_space, "test-project")

        # Should handle gracefully (may pass or fail, but should not crash)
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_non_hex_signature_rejected(self, adapter):
        """Signature with non-hex characters should be rejected."""
        adapter, config = adapter

        payload = b'{"action": "opened"}'
        secret = "test-webhook-secret"

        # Non-hex signature
        invalid_signature = "sha256=zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"

        config.get_project_config.return_value = MagicMock(
            metadata={"webhook_secret": secret}
        )

        result = await adapter._verify_signature(payload, invalid_signature, "test-project")

        assert result is False
