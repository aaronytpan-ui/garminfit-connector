"""
Authentication utilities:
  - Fernet encryption/decryption for garth tokens stored in DB
  - Access token generation for user MCP URLs
"""

import os
import secrets

from cryptography.fernet import Fernet


# ---------------------------------------------------------------------------
# Token encryption
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet:
    key = os.environ.get("TOKEN_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt_token(token_b64: str) -> str:
    """Encrypt a garth dumps() base64 string for storage in the database."""
    return _get_fernet().encrypt(token_b64.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a stored garth token back to a base64 string for garth.loads()."""
    return _get_fernet().decrypt(encrypted.encode()).decode()


# ---------------------------------------------------------------------------
# Access token generation (goes in the user's MCP URL)
# ---------------------------------------------------------------------------

def generate_access_token() -> str:
    """
    Generate a cryptographically random URL-safe token (~22 chars).
    This is the token embedded in the user's MCP URL:
      https://garminfit-connector.railway.app/garmin/?token={access_token}
    """
    return secrets.token_urlsafe(16)  # 16 bytes → ~22 URL-safe chars
