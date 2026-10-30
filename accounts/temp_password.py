"""Starting ("temporary") passwords for students.

SECURITY: a student's starting password used to be her index number, so anyone who knew a classmate's name and index number could
log in as her. Now it is a random-looking 8-character code that only the printed credentials sheet shows.

The code is DERIVED (HMAC of the secret key + username + a counter), not stored, so the sheet can be printed again at any time and
nothing readable sits in the database. Issuing a new one bumps the counter, which invalidates the old code.
"""
import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from .hashers import InitialPasswordHasher

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i look-alikes: it is copied from paper
LENGTH = 8


def derive(username, serial):
    key = settings.SECRET_KEY.encode()
    digest = hmac.new(key, f"amani-start:{str(username).lower()}:{int(serial)}".encode(), hashlib.sha256).digest()
    n = int.from_bytes(digest[:8], "big")
    out = []
    for _ in range(LENGTH):
        n, r = divmod(n, len(ALPHABET))
        out.append(ALPHABET[r])
    return "".join(out)


def password_for(user):
    """What the credentials sheet prints for this student, or None if her password was not issued this way."""
    if not user.temp_issued_at:
        return None
    return derive(user.username, user.temp_serial)


def issue(user, save=True):
    """Give the student a new starting password (she must change it at the first login). Returns the code to print."""
    user.temp_serial = (user.temp_serial or 0) + 1
    user.temp_issued_at = timezone.now()
    code = derive(user.username, user.temp_serial)
    user.password = make_password(code, hasher=InitialPasswordHasher.algorithm)
    user.must_change_password = True
    user.failed_logins, user.locked_until = 0, None
    if save:
        user.save(update_fields=["password", "must_change_password", "temp_serial", "temp_issued_at", "failed_logins", "locked_until"])
    return code


def expired(user, now=None):
    """True when a starting password was never used and is older than TEMP_PASSWORD_TTL_DAYS."""
    days = float(getattr(settings, "TEMP_PASSWORD_TTL_DAYS", 0) or 0)
    if not (days and user.must_change_password and user.temp_issued_at):
        return False
    return (now or timezone.now()) - user.temp_issued_at > timedelta(days=days)
