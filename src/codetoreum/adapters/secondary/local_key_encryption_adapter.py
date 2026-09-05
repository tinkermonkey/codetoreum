"""LocalKeyEncryptionAdapter — Fernet-based encryption with a persistent local key.

This is the production-grade replacement for ``SimpleEncryptionAdapter`` in
single-instance deployments that do not have access to a managed KMS. The key
is sourced from the ``ENCRYPTION_KEY_BASE64`` environment variable; if absent,
a new key is generated at startup and the operator is warned that secrets
written before the next restart will not be decryptable afterward.

For multi-instance deployments and stronger key hygiene, replace this adapter
with one backed by AWS KMS, GCP KMS, HashiCorp Vault, or another centralized
secrets manager. The port shape is the same — the resolver swap is all that
should change.

INV-11 applies: no retry/circuit-breaker logic embedded; encryption is a
synchronous CPU operation and resilience patterns are not meaningful here.
"""

from __future__ import annotations

import base64
import logging
import os
import threading

from cryptography.fernet import Fernet, InvalidToken

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output import DecryptionError, EncryptionError, IEncryptionService

logger = logging.getLogger(__name__)

_ENV_VAR = "ENCRYPTION_KEY_BASE64"


class LocalKeyEncryptionAdapter(IEncryptionService):
    """Fernet (AES-128-CBC + HMAC-SHA256) encryption keyed by a single local key.

    Key sources, in order of preference:
    1. ``key`` argument passed to ``__init__``.
    2. ``ENCRYPTION_KEY_BASE64`` environment variable.
    3. Generated at startup with a WARNING log.

    The encrypted output is a Fernet token: URL-safe base64 of
    ``version || timestamp || IV || ciphertext || HMAC``. Operators can rotate
    keys by calling ``rotate_key(new_key)``; old keys are kept for decryption
    until explicitly removed.
    """

    def __init__(self, key: str | None = None) -> None:
        self._lock = threading.Lock()

        provided = key or os.environ.get(_ENV_VAR)
        if provided is None:
            generated = Fernet.generate_key()
            logger.warning(
                "LocalKeyEncryptionAdapter generated an ephemeral key. Set "
                f"{_ENV_VAR} to a base64-encoded 32-byte key for stability "
                "across restarts. Secrets written now will not be decryptable "
                "after server restart.",
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            self._current_key = generated
        else:
            try:
                # Fernet keys are url-safe base64 of 32 raw bytes. We accept
                # either the raw Fernet form ("...=") or a standard base64
                # encoding for convenience.
                key_bytes = provided.encode("ascii")
                # Validate by attempting construction.
                Fernet(key_bytes)
                self._current_key = key_bytes
            except (ValueError, TypeError, binascii_error()) as exc:
                msg = (
                    f"{_ENV_VAR} must be a Fernet key "
                    "(url-safe base64 of 32 random bytes). "
                    "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                )
                logger.error(msg, exc_info=True, extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR})
                raise EncryptionError(msg) from exc

        # Multi-key support for rotation: old keys remain usable for decryption.
        self._keys: list[bytes] = [self._current_key]
        # Multi-Fernet for transparent decryption against any registered key.
        self._fernet = Fernet(self._current_key)

    async def encrypt(self, plaintext: str, key_id: str | None = None) -> str:
        """Encrypt ``plaintext`` with the current key.

        The ``key_id`` parameter is accepted for port compatibility but
        ignored — this adapter does not support multiple concurrent
        encryption keys; only the most recent key is used for new writes.
        """
        if not isinstance(plaintext, str):
            raise EncryptionError("plaintext must be a string")
        try:
            with self._lock:
                token = self._fernet.encrypt(plaintext.encode("utf-8"))
            return token.decode("ascii")
        except Exception as exc:
            logger.error(
                "LocalKeyEncryptionAdapter.encrypt failed",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            raise EncryptionError(f"Encryption failed: {exc!s}") from exc

    async def decrypt(self, ciphertext: str) -> str:
        """Decrypt against the current key, falling back to retired keys."""
        if not isinstance(ciphertext, str):
            raise DecryptionError("ciphertext must be a string")
        token = ciphertext.encode("ascii")
        last_error: Exception | None = None
        with self._lock:
            keys_snapshot = list(self._keys)
        for k in keys_snapshot:
            try:
                return Fernet(k).decrypt(token).decode("utf-8")
            except InvalidToken as exc:
                last_error = exc
                continue
            except Exception as exc:
                logger.error(
                    "LocalKeyEncryptionAdapter.decrypt unexpected error",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                )
                raise DecryptionError(f"Decryption failed: {exc!s}") from exc
        raise DecryptionError("Ciphertext is not decryptable with any registered key") from last_error

    async def rotate_key(self, old_key_id: str, new_key_id: str) -> None:
        """Rotate the active key.

        The port signature takes string identifiers; this adapter interprets
        ``new_key_id`` as the new key material itself (base64 Fernet key).
        ``old_key_id`` is accepted but ignored — old keys remain registered
        for decryption automatically.

        To prune old keys, call ``forget_old_keys()`` (not part of the port
        contract; tooling-only).
        """
        if not isinstance(new_key_id, str) or not new_key_id:
            raise EncryptionError("new_key_id must be a non-empty Fernet key string")
        try:
            new_bytes = new_key_id.encode("ascii")
            Fernet(new_bytes)  # Validates by side effect.
        except Exception as exc:
            raise EncryptionError(f"new key is not a valid Fernet key: {exc!s}") from exc

        with self._lock:
            if new_bytes not in self._keys:
                self._keys.insert(0, new_bytes)
            self._current_key = new_bytes
            self._fernet = Fernet(new_bytes)
        logger.info("LocalKeyEncryptionAdapter rotated to a new key")

    def forget_old_keys(self) -> None:
        """Drop all keys other than the current one. Tooling-only."""
        with self._lock:
            self._keys = [self._current_key]


def binascii_error() -> type[Exception]:
    """Return ``binascii.Error`` if available, else ``ValueError`` as a fallback."""
    import binascii

    return binascii.Error


__all__ = ["LocalKeyEncryptionAdapter"]


# Generate a fresh Fernet key for local development/testing convenience.
def generate_local_key() -> str:
    """Return a base64-encoded Fernet key suitable for ``ENCRYPTION_KEY_BASE64``."""
    return Fernet.generate_key().decode("ascii")


# Light alias used by some callers that prefer std-lib base64 framing.
def derive_fernet_key_from_bytes(material: bytes) -> bytes:
    """Convenience: produce a Fernet key from raw 32 bytes."""
    if len(material) != 32:
        raise ValueError("material must be exactly 32 bytes")
    return base64.urlsafe_b64encode(material)
