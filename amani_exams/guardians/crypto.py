"""Encryption for parents' names and phone numbers (kept encrypted in the database).

The secret comes from the environment variable GUARDIAN_KEY and is NOT stored in the database, so a stolen
database file or backup alone does not reveal any numbers. Create one with:
    python -c "import secrets; print(secrets.token_urlsafe(48))"
Keep a copy somewhere safe: without it the stored names and numbers can never be read again.
"""
import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _secret() -> bytes:
    raw = getattr(settings, "GUARDIAN_KEY", "")
    if not raw:
        if settings.DEBUG or getattr(settings, "TESTING", False):
            raw = "dev-only-" + settings.SECRET_KEY  # convenient on your own computer, never use this for real data
        else:
            raise ImproperlyConfigured("Set the GUARDIAN_KEY environment variable before storing parents' details.")
    return hashlib.sha256(raw.encode()).digest()


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_secret()))


def encrypt(text: str) -> str:
    return _fernet().encrypt((text or "").encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""  # wrong or missing key: show nothing rather than crash


def blind_index(text: str) -> str:
    """Keyed hash used to find an existing parent by phone number without decrypting everyone."""
    return hmac.new(_secret() + b"|phone-index", (text or "").encode(), hashlib.sha256).hexdigest()
