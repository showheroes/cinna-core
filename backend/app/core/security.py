from datetime import datetime, timedelta, timezone
from typing import Any
import base64

import httpx
import jwt
from authlib.jose import JsonWebToken
from authlib.jose.errors import JoseError
from passlib.context import CryptContext
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


ALGORITHM = "HS256"


# Initialize encryption cipher using the encryption key from settings
def _get_cipher() -> Fernet:
    """Get Fernet cipher instance using the configured encryption key."""
    # Convert the URL-safe base64 key to proper Fernet key format
    key_bytes = settings.ENCRYPTION_KEY.encode()
    # Use PBKDF2 to derive a proper 32-byte key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"credentials_salt",  # Static salt for deterministic key derivation
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(key_bytes))
    return Fernet(key)


def encrypt_field(value: str) -> str:
    """Encrypt a sensitive field value."""
    if not value:
        return value
    cipher = _get_cipher()
    encrypted_bytes = cipher.encrypt(value.encode())
    return encrypted_bytes.decode()


def decrypt_field(encrypted_value: str) -> str:
    """Decrypt a sensitive field value."""
    if not encrypted_value:
        return encrypted_value
    cipher = _get_cipher()
    decrypted_bytes = cipher.decrypt(encrypted_value.encode())
    return decrypted_bytes.decode()


def create_access_token(
    subject: str | Any,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        subject: The ``sub`` claim value (typically a user or token UUID string).
        expires_delta: Token lifetime.
        extra_claims: Optional additional claims merged into the payload before
            signing. Keys that conflict with ``sub`` or ``exp`` are silently
            ignored to prevent accidental claim shadowing.
    """
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode: dict[str, Any] = {}
    if extra_claims:
        # Merge extra claims first so that sub/exp cannot be shadowed.
        to_encode.update(extra_claims)
    to_encode["sub"] = str(subject)
    to_encode["exp"] = expire
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token_claims(token: str) -> dict[str, Any] | None:
    """Decode a JWT and return the full claim dict, or None on any failure.

    Used by the external A2A surface to extract ``client_kind`` and
    ``external_client_id`` claims from desktop-issued access tokens without
    raising an error for ordinary web-session JWTs that omit those claims.

    Returns:
        The full decoded claim dict, or ``None`` if the token cannot be
        decoded (expired, invalid signature, malformed, etc.).
    """
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# Cache for Google public keys (1 hour TTL)
_google_certs_cache: dict[str, Any] = {"certs": None, "expires_at": 0}


async def verify_google_token(token: str, client_id: str) -> dict[str, Any] | None:
    """Verify Google ID token and return claims if valid."""
    try:
        # Fetch Google's public keys (cached for 1 hour)
        now = datetime.now(timezone.utc).timestamp()
        if not _google_certs_cache["certs"] or now >= _google_certs_cache["expires_at"]:
            async with httpx.AsyncClient() as client:
                response = await client.get("https://www.googleapis.com/oauth2/v3/certs")
                _google_certs_cache["certs"] = response.json()
                _google_certs_cache["expires_at"] = now + 3600  # 1 hour

        # Decode and validate token
        jwt_instance = JsonWebToken(["RS256"])
        claims = jwt_instance.decode(
            token,
            _google_certs_cache["certs"],
            claims_options={
                "iss": {"values": ["https://accounts.google.com", "accounts.google.com"]},
                "aud": {"values": [client_id]},
            },
        )
        claims.validate()

        # Require verified email
        if not claims.get("email_verified", False):
            return None

        return dict(claims)
    except JoseError:
        return None
