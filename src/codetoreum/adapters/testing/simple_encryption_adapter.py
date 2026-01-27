"""
Simple Encryption Adapter for Testing and Development

Provides basic AES-256-GCM encryption for sensitive configuration values.

WARNING: This is a simple implementation suitable for testing and development.
For production use, consider:
- Hardware Security Modules (HSM)
- Key Management Services (AWS KMS, Google Cloud KMS, Azure Key Vault)
- Envelope encryption
- Proper key rotation strategies
"""

import base64
import logging
import os
from typing import Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from codetoreum.ports.output import DecryptionError, EncryptionError, IEncryptionService
from codetoreum.infrastructure.error_ids import ErrorRegistry

logger = logging.getLogger(__name__)


class SimpleEncryptionAdapter(IEncryptionService):
    """
    Simple AES-256-GCM encryption adapter.

    Uses AES-256-GCM for authenticated encryption with 96-bit nonces.

    Key Management:
    - Supports multiple encryption keys identified by key_id
    - Default key is used if no key_id is specified
    - Keys are stored in memory (use external KMS for production)

    Encrypted Format:
    - Base64-encoded string containing: key_id:nonce:ciphertext
    - Example: "default:aGVsbG8=:Y2lwaGVy..."
    """

    def __init__(self, default_key: Optional[bytes] = None):
        """
        Initialize the encryption adapter.

        Args:
            default_key: Default 32-byte encryption key. If None, generates a random key.
        """
        self._keys: Dict[str, bytes] = {}

        # Initialize default key
        if default_key is None:
            default_key = AESGCM.generate_key(bit_length=256)
        elif len(default_key) != 32:
            raise ValueError("Encryption key must be 32 bytes for AES-256")

        self._keys["default"] = default_key
        logger.debug("SimpleEncryptionAdapter initialized with default key")

    async def encrypt(self, plaintext: str, key_id: Optional[str] = None) -> str:
        """
        Encrypt a plaintext string using AES-256-GCM.

        Args:
            plaintext: The string to encrypt
            key_id: Optional identifier for encryption key (defaults to "default")

        Returns:
            Base64-encoded encrypted string in format: key_id:nonce:ciphertext

        Raises:
            EncryptionError: If encryption fails
        """
        try:
            # Use default key if not specified
            if key_id is None:
                key_id = "default"

            # Get encryption key
            if key_id not in self._keys:
                raise EncryptionError(f"Unknown encryption key: {key_id}")

            key = self._keys[key_id]

            # Generate random 96-bit nonce
            nonce = os.urandom(12)

            # Encrypt with AES-256-GCM
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

            # Encode as base64: key_id:nonce:ciphertext
            nonce_b64 = base64.b64encode(nonce).decode("utf-8")
            ciphertext_b64 = base64.b64encode(ciphertext).decode("utf-8")
            encrypted = f"{key_id}:{nonce_b64}:{ciphertext_b64}"

            logger.debug(f"Encrypted value using key '{key_id}'")
            return encrypted

        except EncryptionError:
            raise
        except Exception as e:
            logger.error(f"Encryption failed: {e}", extra={"error_id": ErrorRegistry.ErrorRegistry.ERR_INFRASTRUCTURE_ERROR})
            raise EncryptionError(f"Encryption failed: {e}") from e

    async def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a ciphertext string.

        Args:
            ciphertext: Encrypted string in format: key_id:nonce:ciphertext

        Returns:
            The decrypted plaintext string

        Raises:
            DecryptionError: If decryption fails
        """
        try:
            # Parse encrypted format: key_id:nonce:ciphertext
            parts = ciphertext.split(":")
            if len(parts) != 3:
                raise DecryptionError(
                    "Invalid encrypted format. Expected: key_id:nonce:ciphertext"
                )

            key_id, nonce_b64, ciphertext_b64 = parts

            # Get decryption key
            if key_id not in self._keys:
                raise DecryptionError(f"Unknown encryption key: {key_id}")

            key = self._keys[key_id]

            # Decode base64
            nonce = base64.b64decode(nonce_b64)
            ciphertext_bytes = base64.b64decode(ciphertext_b64)

            # Decrypt with AES-256-GCM
            aesgcm = AESGCM(key)
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_bytes, None)

            plaintext = plaintext_bytes.decode("utf-8")
            logger.debug(f"Decrypted value using key '{key_id}'")
            return plaintext

        except DecryptionError:
            raise
        except Exception as e:
            logger.error(f"Decryption failed: {e}", extra={"error_id": ErrorRegistry.ErrorRegistry.ERR_INFRASTRUCTURE_ERROR})
            raise DecryptionError(f"Decryption failed: {e}") from e

    async def rotate_key(self, old_key_id: str, new_key_id: str) -> None:
        """
        Rotate encryption keys.

        Note: This only adds the new key. Actual re-encryption of existing
        values must be done by the calling service.

        Args:
            old_key_id: Identifier of the old encryption key
            new_key_id: Identifier of the new encryption key

        Raises:
            EncryptionError: If key rotation fails
        """
        try:
            if old_key_id not in self._keys:
                raise EncryptionError(f"Unknown old key: {old_key_id}")

            if new_key_id in self._keys:
                raise EncryptionError(f"New key already exists: {new_key_id}")

            # Generate new key
            new_key = AESGCM.generate_key(bit_length=256)
            self._keys[new_key_id] = new_key

            logger.info(f"Rotated encryption key from '{old_key_id}' to '{new_key_id}'")

        except EncryptionError:
            raise
        except Exception as e:
            logger.error(f"Key rotation failed: {e}", extra={"error_id": ErrorRegistry.ErrorRegistry.ERR_INFRASTRUCTURE_ERROR})
            raise EncryptionError(f"Key rotation failed: {e}") from e

    def add_key(self, key_id: str, key: bytes) -> None:
        """
        Add a new encryption key.

        Args:
            key_id: Identifier for the key
            key: 32-byte encryption key

        Raises:
            ValueError: If key is invalid
        """
        if len(key) != 32:
            raise ValueError("Encryption key must be 32 bytes for AES-256")

        if key_id in self._keys:
            raise ValueError(f"Key already exists: {key_id}")

        self._keys[key_id] = key
        logger.debug(f"Added encryption key '{key_id}'")

    def remove_key(self, key_id: str) -> None:
        """
        Remove an encryption key.

        Args:
            key_id: Identifier for the key to remove

        Raises:
            ValueError: If attempting to remove default key
        """
        if key_id == "default":
            raise ValueError("Cannot remove default key")

        if key_id not in self._keys:
            raise ValueError(f"Unknown key: {key_id}")

        del self._keys[key_id]
        logger.debug(f"Removed encryption key '{key_id}'")
