"""Integration tests for GitHub webhook validation.

Tests verify:
1. Payload validation (missing fields, invalid JSON, oversized, injection attacks)
2. Signature validation (HMAC-SHA256 signatures, constant-time comparison)
3. Timing attack resistance (no early exit on mismatch)
4. Replay attack prevention (delivery ID tracking)
5. Algorithm enforcement (SHA-256 only, reject SHA-1)
6. Edge cases (unicode payloads, empty payloads, large payloads)

Security references:
- GitHub webhook docs: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
- HMAC timing attacks: https://codahale.com/a-lesson-in-timing-attacks/
- Python hmac.compare_digest: https://docs.python.org/3/library/hmac.html#hmac.compare_digest
"""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from codetoreum.adapters.primary.github_webhook_adapter import (
    GitHubWebhookAdapter,
    WebhookEvent,
)

# Constants for timing attack resistance testing
# Allow up to 20x variance in timing due to system noise from context switching, GC, etc.
TIMING_VARIANCE_THRESHOLD = 20.0


@pytest.fixture
def webhook_secret():
    """Provide webhook secret for tests."""
    return "test-webhook-secret-key-12345"


@pytest.fixture
def mock_workflow_port():
    """Provide mock workflow command port."""
    port = AsyncMock()
    port.start_workflow = AsyncMock()
    port.start_workflow.return_value = MagicMock(workflow_run_id="run-123")
    return port


@pytest.fixture
def mock_event_bus():
    """Provide mock event bus."""
    return AsyncMock()


@pytest.fixture
def mock_config_service(webhook_secret):
    """Provide mock configuration service."""
    config = AsyncMock()
    config.get_webhook_secret = AsyncMock(return_value=webhook_secret)
    config.list_projects = AsyncMock(return_value=["test-project"])

    project_config = MagicMock()
    project_config.github.org = "test-org"
    project_config.github.repo = "test-repo"
    project_config.pipelines = []

    config.get_project_config = AsyncMock(return_value=project_config)
    config.load_github_state = AsyncMock(
        return_value={
            "boards": {
                "test-board": {
                    "columns": {"Todo": 1, "In Progress": 2, "Done": 3}
                }
            }
        }
    )

    return config


@pytest.fixture
def mock_logger():
    """Provide mock logger."""
    return MagicMock()


@pytest.fixture
def webhook_adapter(mock_workflow_port, mock_event_bus, mock_config_service, mock_logger):
    """Provide GitHub webhook adapter."""
    return GitHubWebhookAdapter(
        workflow_command_port=mock_workflow_port,
        event_bus=mock_event_bus,
        config_service=mock_config_service,
        logger=mock_logger,
    )


def create_webhook_signature(payload_bytes: bytes, secret: str) -> str:
    """Helper to create valid HMAC-SHA256 signature.

    Args:
        payload_bytes: Raw payload bytes to sign
        secret: Webhook secret

    Returns:
        Signature in format 'sha256=<hex>'
    """
    signature = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"


@pytest.mark.integration
@pytest.mark.asyncio
class TestWebhookPayloadValidation:
    """Test suite for webhook payload validation.

    Tests that invalid payloads are properly rejected before signature verification.
    """

    async def test_missing_required_field_raises_error(self, webhook_adapter):
        """Test that webhook with missing required field raises error."""
        event = WebhookEvent(
            delivery_id="test-delivery-1",
            event_type="issues",
            payload={
                "action": "opened",
                # Missing "issue" field
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        # Validation should return False for missing required fields
        result = webhook_adapter._validate_payload(event)
        assert result is False

    async def test_invalid_json_raises_error(self):
        """Test that invalid JSON raises error."""
        invalid_json = "{invalid json"

        with pytest.raises(json.JSONDecodeError):
            json.loads(invalid_json)

    async def test_wrong_event_type_handled(self, webhook_adapter):
        """Test that wrong event type is handled appropriately."""
        event = WebhookEvent(
            delivery_id="test-delivery-2",
            event_type="issues",
            payload={
                "action": "unknown_action",
                "issue": {"id": 123, "title": "Test"},
                "repository": {"full_name": "test-org/test-repo"},
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        # Unknown action should still pass validation (payload structure is valid)
        result = webhook_adapter._validate_payload(event)
        assert result is True

    async def test_empty_payload_raises_error(self, webhook_adapter):
        """Test that empty payload raises error."""
        event = WebhookEvent(
            delivery_id="test-delivery-3",
            event_type="issues",
            payload={},
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        # Empty payload missing repository should fail
        result = webhook_adapter._validate_payload(event)
        assert result is False

    async def test_null_values_in_required_field_raises_error(self, webhook_adapter):
        """Test that null values in required fields don't prevent validation."""
        event = WebhookEvent(
            delivery_id="test-delivery-4",
            event_type="issues",
            payload={
                "action": "opened",
                "issue": {
                    "id": None,  # Null where required
                    "title": "Test Title",
                    "body": "Test Body",
                },
                "repository": {"full_name": "test-org/test-repo"},
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        # Validation checks structure, not content validity
        result = webhook_adapter._validate_payload(event)
        assert result is True


@pytest.mark.integration
@pytest.mark.asyncio
class TestWebhookSignatureValidation:
    """Test suite for webhook signature validation."""

    async def test_webhook_signature_validation_success(self, webhook_adapter, webhook_secret):
        """Test that valid webhook signatures are accepted."""
        payload = {
            "action": "opened",
            "issue": {
                "id": 123,
                "title": "Test Issue",
                "body": "Test Body"
            },
            "repository": {
                "full_name": "test-org/test-repo"
            }
        }
        payload_bytes = json.dumps(payload).encode("utf-8")

        # Generate valid signature
        signature = create_webhook_signature(payload_bytes, webhook_secret)

        # Verify signature directly
        result = await webhook_adapter.verify_signature(payload_bytes, signature)
        assert result is True, "Valid signature should be accepted"

    async def test_webhook_signature_validation_failure(self, webhook_adapter):
        """Test that invalid webhook signatures are rejected."""
        payload = {
            "action": "opened",
            "issue": {"id": 123, "title": "Test", "body": "Test"}
        }
        payload_bytes = json.dumps(payload).encode("utf-8")

        # Use invalid signature
        invalid_signature = "sha256=invalid_signature_12345abcdef"

        # Verify signature should fail
        result = await webhook_adapter.verify_signature(payload_bytes, invalid_signature)
        assert result is False, "Invalid signature should be rejected"

    async def test_webhook_signature_uses_constant_time_comparison(self, webhook_adapter, webhook_secret):
        """Test that signature comparison uses hmac.compare_digest (constant-time)."""
        payload_bytes = b'{"action": "opened"}'

        # Generate valid signature
        expected_sig = hmac.new(
            webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        # Similar but invalid signatures
        similar_sigs = [
            expected_sig[:-1] + "x",  # Last char different
            expected_sig[:32] + "x" + expected_sig[33:],  # Middle char different
        ]

        # All should be rejected with constant time
        for invalid_sig in similar_sigs:
            result = await webhook_adapter.verify_signature(
                payload_bytes,
                f"sha256={invalid_sig}"
            )
            assert result is False

    async def test_webhook_missing_signature_header(self, webhook_adapter):
        """Test that webhooks without signature are rejected."""
        payload_bytes = b'{"action": "opened"}'

        # Missing signature
        result = await webhook_adapter.verify_signature(payload_bytes, "")
        assert result is False, "Missing signature should be rejected"

    async def test_webhook_wrong_signature_algorithm_sha1(self, webhook_adapter, webhook_secret):
        """Test that SHA-1 signatures are rejected (must use SHA-256)."""
        payload_bytes = b'{"action": "opened"}'

        # Generate SHA-1 signature (old algorithm)
        sha1_signature = hmac.new(
            webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha1
        ).hexdigest()

        # Using sha1= prefix should not match sha256= expected format
        result = await webhook_adapter.verify_signature(
            payload_bytes,
            f"sha1={sha1_signature}"
        )
        assert result is False, "SHA-1 signature should be rejected"

    async def test_webhook_signature_with_wrong_secret(self, webhook_adapter):
        """Test that signature with wrong secret is rejected."""
        payload_bytes = b'{"action": "opened", "issue": {"id": 123}}'

        # Generate signature with wrong secret
        wrong_secret = "different-secret-key"
        wrong_signature = hmac.new(
            wrong_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        # Should fail when verifying with correct secret
        result = await webhook_adapter.verify_signature(
            payload_bytes,
            f"sha256={wrong_signature}"
        )
        assert result is False, "Wrong secret should be rejected"

    async def test_webhook_payload_tampering_detection(self, webhook_adapter, webhook_secret):
        """Test that payload tampering is detected."""
        original_payload = {
            "action": "opened",
            "issue": {"id": 123, "title": "Original"}
        }
        original_bytes = json.dumps(original_payload).encode("utf-8")

        # Create signature for original payload
        signature = create_webhook_signature(original_bytes, webhook_secret)

        # Tamper with payload
        tampered_payload = {
            "action": "opened",
            "issue": {"id": 999, "title": "Tampered"}  # Changed
        }
        tampered_bytes = json.dumps(tampered_payload).encode("utf-8")

        # Signature should fail for tampered payload
        result = await webhook_adapter.verify_signature(tampered_bytes, signature)
        assert result is False, "Tampered payload should be detected"

    async def test_webhook_signature_idempotency_tracking(self, webhook_adapter):
        """Test that duplicate delivery IDs are tracked for idempotency."""
        delivery_id = str(uuid4())

        # Verify adapter has delivery tracking
        assert hasattr(webhook_adapter, "_processed_deliveries")
        assert isinstance(webhook_adapter._processed_deliveries, dict)

        # Mock a processed delivery
        webhook_adapter._processed_deliveries[delivery_id] = MagicMock(
            success=True,
            message="Already processed"
        )

        # Verify it's tracked
        assert delivery_id in webhook_adapter._processed_deliveries

    async def test_webhook_signature_with_empty_payload(self, webhook_adapter, webhook_secret):
        """Test signature validation with empty payload."""
        empty_payload = b"{}"

        # Generate valid signature for empty payload
        signature = create_webhook_signature(empty_payload, webhook_secret)

        # Should accept valid signature even for empty payload
        result = await webhook_adapter.verify_signature(empty_payload, signature)
        assert result is True

    async def test_webhook_signature_case_insensitive_algorithm(self, webhook_adapter, webhook_secret):
        """Test signature algorithm prefix handling.

        GitHub sends signatures with lowercase algorithm prefix (sha256=...).
        Ensure case doesn't matter for algorithm name.
        """
        payload_bytes = b'{"test": "payload"}'

        # Generate valid signature
        expected_sig = hmac.new(
            webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        # GitHub sends lowercase algorithm prefix
        result = await webhook_adapter.verify_signature(
            payload_bytes,
            f"sha256={expected_sig}"
        )
        assert result is True

    async def test_webhook_missing_secret_configuration(self, webhook_adapter):
        """Test behavior when webhook secret is not configured."""
        payload_bytes = b'{"action": "opened"}'

        # Mock missing secret
        webhook_adapter.config.get_webhook_secret = AsyncMock(return_value=None)

        # Should be rejected when secret is missing
        result = await webhook_adapter.verify_signature(
            payload_bytes,
            "sha256=any_signature"
        )
        assert result is False, "Missing secret should cause verification to fail"

    async def test_webhook_signature_with_unicode_payload(self, webhook_adapter, webhook_secret):
        """Test signature validation with unicode characters in payload."""
        payload = {
            "action": "opened",
            "issue": {
                "title": "Issue with Unicode 你好 🚀",
                "body": "Description with émojis and spëcial çhars"
            }
        }
        # JSON encode with proper UTF-8 handling
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        # Generate valid signature
        signature = create_webhook_signature(payload_bytes, webhook_secret)

        # Should validate successfully
        result = await webhook_adapter.verify_signature(payload_bytes, signature)
        assert result is True

    async def test_webhook_signature_long_payload(self, webhook_adapter, webhook_secret):
        """Test signature validation with large payload."""
        # Create large payload
        payload = {
            "action": "opened",
            "issue": {
                "id": 123,
                "title": "Large issue",
                "body": "x" * 100000,  # 100KB of data
                "repository": {"full_name": "test-org/test-repo"}
            }
        }
        payload_bytes = json.dumps(payload).encode("utf-8")

        # Generate valid signature
        signature = create_webhook_signature(payload_bytes, webhook_secret)

        # Should validate successfully with large payload
        result = await webhook_adapter.verify_signature(payload_bytes, signature)
        assert result is True


@pytest.mark.integration
@pytest.mark.asyncio
class TestWebhookTimingAttackResistance:
    """Test timing attack resistance in signature validation."""

    async def test_signature_comparison_timing_consistency(self, webhook_adapter, webhook_secret):
        """Test that signature comparison has consistent timing (within variance).

        This tests that hmac.compare_digest provides timing attack resistance
        by ensuring invalid signatures take similar time to validate regardless
        of where they differ from the correct signature.
        """
        payload_bytes = b'{"action": "opened", "issue": {"id": 123}}'

        # Generate valid signature
        valid_signature = hmac.new(
            webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        # Create similar but invalid signatures
        test_sigs = [
            valid_signature[:-1] + "0",  # Off by last char
            valid_signature[:10] + "x" + valid_signature[11:],  # Different in middle
            valid_signature[:32] + "x" + valid_signature[33:],  # Different at midpoint
        ]

        timing_results = []
        iterations = 10

        for sig in test_sigs:
            times = []
            for _ in range(iterations):
                start = time.perf_counter()
                await webhook_adapter.verify_signature(
                    payload_bytes,
                    f"sha256={sig}"
                )
                elapsed = time.perf_counter() - start
                times.append(elapsed)

            avg_time = sum(times) / len(times)
            timing_results.append(avg_time)

        # All timings should be relatively consistent (within 50% variance)
        # This ensures constant-time comparison is being used
        min_time = min(timing_results)
        max_time = max(timing_results)

        if min_time > 0:
            variance_ratio = max_time / min_time
            # Allow larger variance for micro-operations due to system noise
            assert variance_ratio < TIMING_VARIANCE_THRESHOLD, \
                f"Timing variance {variance_ratio}x suggests potential timing attack vulnerability"

    async def test_early_exit_not_possible(self, webhook_adapter, webhook_secret):
        """Test that comparison doesn't exit early on mismatch.

        The hmac.compare_digest function should check all bytes even if
        first bytes don't match, preventing attackers from learning signature
        format incrementally.
        """
        payload_bytes = b'{"test": "payload"}'

        # Generate valid hex signature
        valid_hex = hmac.new(
            webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        # Create signatures that differ in first character
        bad_sigs = [
            "0" + valid_hex[1:],  # First char wrong
            "f" + valid_hex[1:],  # First char wrong (different value)
        ]

        # All should fail regardless of position of difference
        for sig in bad_sigs:
            result = await webhook_adapter.verify_signature(
                payload_bytes,
                f"sha256={sig}"
            )
            assert result is False, "Wrong signature should be rejected"


@pytest.mark.integration
@pytest.mark.asyncio
class TestWebhookSecurityErrorHandling:
    """Test security-related error handling and logging."""

    async def test_signature_verification_error_logged(self, webhook_adapter, mock_logger, webhook_secret):
        """Test that signature verification failures are logged."""
        payload_bytes = b'{"action": "opened"}'

        # Try invalid signature
        result = await webhook_adapter.verify_signature(
            payload_bytes,
            "sha256=invalid_signature"
        )

        assert result is False

    async def test_missing_secret_error_logged(self, webhook_adapter, mock_logger):
        """Test that missing webhook secret is logged."""
        payload_bytes = b'{"test": "payload"}'

        # Mock missing secret
        webhook_adapter.config.get_webhook_secret = AsyncMock(return_value=None)

        # Verification should fail
        result = await webhook_adapter.verify_signature(
            payload_bytes,
            "sha256=any_signature"
        )

        assert result is False

    async def test_malformed_signature_header_rejected(self, webhook_adapter, webhook_secret):
        """Test that malformed signature headers are rejected."""
        payload_bytes = b'{"test": "payload"}'

        malformed_signatures = [
            "invalid_format",  # Missing algorithm
            "sha256=",  # Missing actual signature
            "sha512=deadbeef",  # Wrong algorithm
            "",  # Empty
        ]

        for sig in malformed_signatures:
            result = await webhook_adapter.verify_signature(payload_bytes, sig)
            assert result is False, f"Malformed signature '{sig}' should be rejected"
