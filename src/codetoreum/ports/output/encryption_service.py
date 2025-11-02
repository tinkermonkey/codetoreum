"""
Encryption Service Output Port Interface

Provides encryption/decryption capabilities for sensitive configuration values.
"""

from abc import ABC, abstractmethod
from typing import Optional


class IEncryptionService(ABC):
    """
    Output port for encryption operations.

    Used for encrypting sensitive configuration values (API keys, secrets, etc.)
    before storage and decrypting them when retrieved.
    """

    @abstractmethod
    async def encrypt(self, plaintext: str, key_id: Optional[str] = None) -> str:
        """
        Encrypt a plaintext string.

        Args:
            plaintext: The string to encrypt
            key_id: Optional identifier for encryption key (for key rotation support)

        Returns:
            The encrypted string (typically base64-encoded ciphertext)

        Raises:
            EncryptionError: If encryption fails
        """
        pass

    @abstractmethod
    async def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a ciphertext string.

        Args:
            ciphertext: The encrypted string to decrypt

        Returns:
            The decrypted plaintext string

        Raises:
            DecryptionError: If decryption fails
        """
        pass

    @abstractmethod
    async def rotate_key(self, old_key_id: str, new_key_id: str) -> None:
        """
        Rotate encryption keys.

        Args:
            old_key_id: Identifier of the old encryption key
            new_key_id: Identifier of the new encryption key

        Raises:
            EncryptionError: If key rotation fails
        """
        pass


class EncryptionError(Exception):
    """Raised when encryption operations fail."""
    pass


class DecryptionError(Exception):
    """Raised when decryption operations fail."""
    pass
