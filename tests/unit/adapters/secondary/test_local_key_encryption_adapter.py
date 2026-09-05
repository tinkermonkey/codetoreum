"""Unit tests for LocalKeyEncryptionAdapter."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

from codetoreum.adapters.secondary.local_key_encryption_adapter import (
    LocalKeyEncryptionAdapter,
    generate_local_key,
)
from codetoreum.ports.output import DecryptionError, EncryptionError


class TestLocalKeyEncryptionAdapterRoundTrip:
    @pytest.mark.asyncio
    async def test_encrypt_decrypt_round_trip_with_explicit_key(self) -> None:
        key = generate_local_key()
        adapter = LocalKeyEncryptionAdapter(key=key)

        ciphertext = await adapter.encrypt("super-secret-token")
        assert ciphertext != "super-secret-token"
        plaintext = await adapter.decrypt(ciphertext)
        assert plaintext == "super-secret-token"

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_with_env_var(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        key = generate_local_key()
        monkeypatch.setenv("ENCRYPTION_KEY_BASE64", key)
        adapter = LocalKeyEncryptionAdapter()

        ciphertext = await adapter.encrypt("env-key-secret")
        assert await adapter.decrypt(ciphertext) == "env-key-secret"

    @pytest.mark.asyncio
    async def test_ephemeral_key_when_env_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.delenv("ENCRYPTION_KEY_BASE64", raising=False)
        with caplog.at_level("WARNING"):
            adapter = LocalKeyEncryptionAdapter()

        assert any("generated an ephemeral key" in r.message for r in caplog.records)

        # Same adapter instance can decrypt what it encrypted.
        ct = await adapter.encrypt("ephemeral")
        assert await adapter.decrypt(ct) == "ephemeral"


class TestLocalKeyEncryptionAdapterInvalidInput:
    @pytest.mark.asyncio
    async def test_invalid_env_var_key_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ENCRYPTION_KEY_BASE64", "not-a-real-key")
        with pytest.raises(EncryptionError):
            LocalKeyEncryptionAdapter()

    @pytest.mark.asyncio
    async def test_encrypt_rejects_non_string(self) -> None:
        adapter = LocalKeyEncryptionAdapter(key=generate_local_key())
        with pytest.raises(EncryptionError):
            await adapter.encrypt(b"not-a-string")

    @pytest.mark.asyncio
    async def test_decrypt_corrupt_ciphertext_raises(self) -> None:
        adapter = LocalKeyEncryptionAdapter(key=generate_local_key())
        with pytest.raises(DecryptionError):
            await adapter.decrypt("not-a-valid-fernet-token")

    @pytest.mark.asyncio
    async def test_decrypt_with_wrong_key_raises(self) -> None:
        a1 = LocalKeyEncryptionAdapter(key=generate_local_key())
        a2 = LocalKeyEncryptionAdapter(key=generate_local_key())

        ct = await a1.encrypt("hello")
        with pytest.raises(DecryptionError):
            await a2.decrypt(ct)


class TestLocalKeyEncryptionAdapterKeyRotation:
    @pytest.mark.asyncio
    async def test_rotate_key_allows_decryption_of_old_ciphertext(self) -> None:
        old_key = generate_local_key()
        new_key = generate_local_key()
        adapter = LocalKeyEncryptionAdapter(key=old_key)

        ct_old = await adapter.encrypt("encrypted-with-old-key")
        await adapter.rotate_key(old_key_id=old_key, new_key_id=new_key)

        # New writes use the new key
        ct_new = await adapter.encrypt("encrypted-with-new-key")
        # Both can be decrypted
        assert await adapter.decrypt(ct_old) == "encrypted-with-old-key"
        assert await adapter.decrypt(ct_new) == "encrypted-with-new-key"

    @pytest.mark.asyncio
    async def test_rotate_to_invalid_key_raises(self) -> None:
        adapter = LocalKeyEncryptionAdapter(key=generate_local_key())
        with pytest.raises(EncryptionError):
            await adapter.rotate_key(old_key_id="ignored", new_key_id="bogus")

    @pytest.mark.asyncio
    async def test_forget_old_keys_drops_decryption_capability(self) -> None:
        old_key = generate_local_key()
        new_key = generate_local_key()
        adapter = LocalKeyEncryptionAdapter(key=old_key)
        ct_old = await adapter.encrypt("encrypted-with-old-key")
        await adapter.rotate_key(old_key_id=old_key, new_key_id=new_key)
        adapter.forget_old_keys()
        with pytest.raises(DecryptionError):
            await adapter.decrypt(ct_old)


class TestLocalKeyEncryptionAdapterPortContract:
    """Confirm IEncryptionService contract is honored."""

    def test_inherits_iencryption_service(self) -> None:
        from codetoreum.ports.output import IEncryptionService

        adapter = LocalKeyEncryptionAdapter(key=generate_local_key())
        assert isinstance(adapter, IEncryptionService)
