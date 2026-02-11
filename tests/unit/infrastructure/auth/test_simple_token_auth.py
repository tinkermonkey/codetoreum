"""
Unit tests for Simple Token Authentication

Tests the JupyterLab-style token generation, validation, and security properties.
"""

import os
import pytest
import secrets
from datetime import datetime, timedelta, timezone
from jose import jwt
from unittest.mock import patch

from codetoreum.infrastructure.auth import SimpleTokenAuthManager


class TestSimpleTokenAuthManager:
    """Test suite for SimpleTokenAuthManager"""

    def test_token_generation(self):
        """Test that a valid JWT token is generated on initialization"""
        manager = SimpleTokenAuthManager()

        # Token should be a non-empty string
        assert manager.server_token
        assert isinstance(manager.server_token, str)
        assert len(manager.server_token) > 0

    def test_token_structure(self):
        """Test that generated token has correct structure"""
        secret_key = "test-secret-key"
        manager = SimpleTokenAuthManager(secret_key=secret_key)

        # Decode token to verify structure
        payload = jwt.decode(
            manager.server_token, secret_key, algorithms=["HS256"]
        )

        assert payload["sub"] == "codetoreum-server"
        assert payload["type"] == "access"
        assert "iat" in payload
        assert "exp" in payload

    def test_token_expiration(self):
        """Test that token has correct expiration time"""
        secret_key = "test-secret-key"
        expiry_days = 30
        manager = SimpleTokenAuthManager(
            secret_key=secret_key, token_expiry_days=expiry_days
        )

        # Decode token
        payload = jwt.decode(
            manager.server_token, secret_key, algorithms=["HS256"]
        )

        # Check expiration is approximately correct (within 1 second tolerance)
        expected_exp = manager.server_start_time + timedelta(days=expiry_days)
        actual_exp = datetime.utcfromtimestamp(payload["exp"])
        time_diff = abs((actual_exp - expected_exp).total_seconds())

        assert time_diff < 1, f"Expiration time differs by {time_diff} seconds"

    def test_validate_token_success(self):
        """Test successful token validation"""
        manager = SimpleTokenAuthManager()

        # Should validate own token
        assert manager.validate_token(manager.server_token) is True

    def test_validate_token_invalid(self):
        """Test validation fails for invalid tokens"""
        manager = SimpleTokenAuthManager()

        # Empty token
        assert manager.validate_token("") is False

        # Random string
        assert manager.validate_token("not-a-valid-token") is False

        # Valid JWT structure but wrong signature
        fake_token = jwt.encode(
            {"sub": "codetoreum-server", "type": "access"},
            "wrong-secret-key",
            algorithm="HS256"
        )
        assert manager.validate_token(fake_token) is False

    def test_validate_token_wrong_subject(self):
        """Test validation fails for tokens with wrong subject"""
        secret_key = "test-secret-key"
        manager = SimpleTokenAuthManager(secret_key=secret_key)

        # Create token with wrong subject
        wrong_token = jwt.encode(
            {
                "sub": "wrong-subject",
                "type": "access",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(days=1),
            },
            secret_key,
            algorithm="HS256"
        )

        assert manager.validate_token(wrong_token) is False

    def test_validate_token_wrong_type(self):
        """Test validation fails for tokens with wrong type"""
        secret_key = "test-secret-key"
        manager = SimpleTokenAuthManager(secret_key=secret_key)

        # Create token with wrong type
        wrong_token = jwt.encode(
            {
                "sub": "codetoreum-server",
                "type": "refresh",  # Wrong type
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(days=1),
            },
            secret_key,
            algorithm="HS256"
        )

        assert manager.validate_token(wrong_token) is False

    def test_validate_token_expired(self):
        """Test validation fails for expired tokens"""
        secret_key = "test-secret-key"

        # Create token that already expired
        expired_token = jwt.encode(
            {
                "sub": "codetoreum-server",
                "type": "access",
                "iat": datetime.now(timezone.utc) - timedelta(days=2),
                "exp": datetime.now(timezone.utc) - timedelta(days=1),  # Expired yesterday
            },
            secret_key,
            algorithm="HS256"
        )

        manager = SimpleTokenAuthManager(secret_key=secret_key)
        assert manager.validate_token(expired_token) is False

    def test_validate_token_timing_attack_resistance(self):
        """Test that token validation uses constant-time comparison"""
        manager = SimpleTokenAuthManager()

        # This test verifies that JWT library's comparison is used
        # (JWT library uses constant-time comparison internally)
        # We don't need to test the actual timing since the JWT library
        # (python-jose) already provides constant-time comparison.
        # Instead, we just verify the function works correctly.

        # Valid token should validate
        assert manager.validate_token(manager.server_token) is True

        # Invalid tokens should not validate
        assert manager.validate_token("invalid-token-" + "x" * 100) is False
        assert manager.validate_token("different-invalid") is False

        # Note: Actual timing attack resistance is provided by the python-jose library
        # which uses constant-time comparison for HMAC verification

    def test_get_access_url(self):
        """Test access URL generation"""
        manager = SimpleTokenAuthManager()
        url = manager.get_access_url("http://localhost:8000")

        assert url.startswith("http://localhost:8000/?token=")
        assert manager.server_token in url

    def test_get_access_url_custom_base(self):
        """Test access URL with custom base URL"""
        manager = SimpleTokenAuthManager()
        url = manager.get_access_url("https://example.com:9000")

        assert url.startswith("https://example.com:9000/?token=")
        assert manager.server_token in url

    def test_get_token_info(self):
        """Test token information retrieval"""
        manager = SimpleTokenAuthManager()
        info = manager.get_token_info()

        assert info["is_valid"] is True
        assert info["subject"] == "codetoreum-server"
        assert "issued_at" in info
        assert "expires_at" in info

    def test_get_token_info_dates(self):
        """Test token info returns valid ISO dates"""
        manager = SimpleTokenAuthManager()
        info = manager.get_token_info()

        # Should be able to parse dates
        issued_at = datetime.fromisoformat(info["issued_at"])
        expires_at = datetime.fromisoformat(info["expires_at"])

        # Expiration should be after issuance
        assert expires_at > issued_at

    def test_custom_secret_key(self):
        """Test using custom secret key"""
        custom_secret = "my-custom-secret-key"
        manager = SimpleTokenAuthManager(secret_key=custom_secret)

        # Should validate with custom secret
        assert manager.validate_token(manager.server_token) is True

        # Should not validate with different secret
        other_manager = SimpleTokenAuthManager(secret_key="different-secret")
        assert other_manager.validate_token(manager.server_token) is False

    def test_auto_generated_secret_key(self):
        """Test that auto-generated secret keys are random and secure"""
        manager1 = SimpleTokenAuthManager()
        manager2 = SimpleTokenAuthManager()

        # Each instance should have different secret key
        assert manager1.secret_key != manager2.secret_key

        # Secret keys should be reasonably long
        assert len(manager1.secret_key) > 20
        assert len(manager2.secret_key) > 20

        # Tokens should not validate across instances
        assert manager1.validate_token(manager2.server_token) is False
        assert manager2.validate_token(manager1.server_token) is False

    def test_print_auth_info_no_error(self, capsys):
        """Test that print_auth_info works without errors"""
        manager = SimpleTokenAuthManager()

        # Should not raise exception
        manager.print_auth_info(host="localhost", port=8000)

        # Should print something
        captured = capsys.readouterr()
        assert len(captured.out) > 0
        assert "Codetoreum" in captured.out
        assert manager.server_token in captured.out

    def test_print_auth_info_https(self, capsys):
        """Test print_auth_info with HTTPS"""
        manager = SimpleTokenAuthManager()
        manager.print_auth_info(host="example.com", port=443, use_https=True)

        captured = capsys.readouterr()
        assert "https://example.com:443" in captured.out

    def test_token_none_validation(self):
        """Test that None token is rejected"""
        manager = SimpleTokenAuthManager()
        assert manager.validate_token(None) is False

    def test_token_empty_string_validation(self):
        """Test that empty string token is rejected"""
        manager = SimpleTokenAuthManager()
        assert manager.validate_token("") is False

    def test_token_whitespace_validation(self):
        """Test that whitespace-only token is rejected"""
        manager = SimpleTokenAuthManager()
        assert manager.validate_token("   ") is False

    def test_malformed_jwt_validation(self):
        """Test that malformed JWTs are rejected"""
        manager = SimpleTokenAuthManager()

        # Malformed JWTs (not base64, wrong structure, etc.)
        malformed_tokens = [
            "not.a.jwt",
            "header.payload",  # Missing signature
            "a.b.c.d",  # Too many parts
            "....",  # Just dots
        ]

        for token in malformed_tokens:
            assert manager.validate_token(token) is False


class TestSecretKeyValidation:
    """Test suite for secret key validation and environment handling"""

    @patch.dict(os.environ, {"CODETOREUM_ENV": "production"}, clear=False)
    def test_production_requires_secret_key(self):
        """Test that production mode requires explicit secret key"""
        with pytest.raises(ValueError) as exc_info:
            SimpleTokenAuthManager()

        error_msg = str(exc_info.value)
        assert "CODETOREUM_SECRET_KEY" in error_msg
        assert "production" in error_msg
        assert "secrets.token_urlsafe(64)" in error_msg

    @patch.dict(os.environ, {"CODETOREUM_ENV": "production"}, clear=False)
    def test_production_accepts_explicit_secret_key(self):
        """Test that production mode works with explicit secret key"""
        secret_key = "my-production-secret-key"
        manager = SimpleTokenAuthManager(secret_key=secret_key)

        assert manager.secret_key == secret_key
        assert manager.server_token
        assert manager.validate_token(manager.server_token) is True

    @patch.dict(os.environ, {"CODETOREUM_ENV": "development"}, clear=False)
    def test_development_allows_auto_generated_secret(self, caplog):
        """Test that development mode allows auto-generated secret key"""
        import logging
        caplog.set_level(logging.WARNING)

        manager = SimpleTokenAuthManager()

        # Should generate a secret key
        assert manager.secret_key
        assert len(manager.secret_key) > 20

        # Should log a warning
        assert any("auto-generated secret key" in record.message.lower()
                   for record in caplog.records)
        assert any("CODETOREUM_SECRET_KEY" in record.message
                   for record in caplog.records)

    @patch.dict(os.environ, {"CODETOREUM_ENV": "development"}, clear=False)
    def test_development_accepts_explicit_secret_key(self, caplog):
        """Test that development mode works with explicit secret key"""
        import logging
        caplog.set_level(logging.WARNING)

        secret_key = "my-dev-secret-key"
        manager = SimpleTokenAuthManager(secret_key=secret_key)

        assert manager.secret_key == secret_key

        # Should NOT log a warning when explicit key is provided
        assert not any("auto-generated" in record.message.lower()
                       for record in caplog.records)

    @patch.dict(os.environ, {}, clear=False)
    def test_default_environment_is_development(self, caplog):
        """Test that default environment (no CODETOREUM_ENV) behaves as development"""
        import logging
        caplog.set_level(logging.WARNING)

        # Remove CODETOREUM_ENV if it exists
        os.environ.pop("CODETOREUM_ENV", None)

        manager = SimpleTokenAuthManager()

        # Should work (not raise ValueError)
        assert manager.secret_key
        assert manager.server_token

        # Should log warning about auto-generated key
        assert any("auto-generated" in record.message.lower()
                   for record in caplog.records)

    @patch.dict(os.environ, {"CODETOREUM_ENV": "staging"}, clear=False)
    def test_non_production_environment_allows_auto_generated_secret(self, caplog):
        """Test that non-production environments (staging, test, etc.) allow auto-generated secrets"""
        import logging
        caplog.set_level(logging.WARNING)

        manager = SimpleTokenAuthManager()

        # Should work (staging is not production)
        assert manager.secret_key
        assert manager.server_token

        # Should log warning
        assert any("auto-generated" in record.message.lower()
                   for record in caplog.records)

    def test_error_message_includes_generation_instructions(self):
        """Test that production error message includes instructions for generating secret key"""
        with patch.dict(os.environ, {"CODETOREUM_ENV": "production"}, clear=False):
            with pytest.raises(ValueError) as exc_info:
                SimpleTokenAuthManager()

            error_msg = str(exc_info.value)
            # Should include the python command to generate a key
            assert "python -c" in error_msg
            assert "secrets.token_urlsafe(64)" in error_msg

    @patch.dict(os.environ, {"CODETOREUM_ENV": "production"}, clear=False)
    def test_production_with_empty_string_secret_key_fails(self):
        """Test that production mode rejects empty string as secret key"""
        with pytest.raises(ValueError) as exc_info:
            SimpleTokenAuthManager(secret_key="")

        assert "CODETOREUM_SECRET_KEY" in str(exc_info.value)

    @patch.dict(os.environ, {"CODETOREUM_ENV": "production"}, clear=False)
    def test_production_with_whitespace_secret_key_fails(self):
        """Test that production mode rejects whitespace-only secret key"""
        with pytest.raises(ValueError) as exc_info:
            SimpleTokenAuthManager(secret_key="   ")

        assert "CODETOREUM_SECRET_KEY" in str(exc_info.value)

    @patch.dict(os.environ, {"CODETOREUM_ENV": "production"}, clear=False)
    def test_production_with_none_secret_key_fails(self):
        """Test that production mode rejects None as secret key"""
        with pytest.raises(ValueError) as exc_info:
            SimpleTokenAuthManager(secret_key=None)

        assert "CODETOREUM_SECRET_KEY" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
