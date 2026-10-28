from django.contrib.auth.hashers import PBKDF2PasswordHasher


class InitialPasswordHasher(PBKDF2PasswordHasher):
    """Lighter PBKDF2 used only for starting passwords of bulk-uploaded students.
    Never the preferred hasher, so Django upgrades it on the first successful login."""

    algorithm = "pbkdf2_sha256_initial"
    iterations = 100_000


class StrongPasswordHasher(PBKDF2PasswordHasher):
    """The preferred hasher: PBKDF2-SHA256 with 600,000 iterations (the OWASP recommendation).
    Django's own default is 1,000,000, which costs about 0.3 s of processor time per login; with hundreds of
    students logging in during the same minute that dominates the load (NFR-05). Older hashes still verify and
    are upgraded to this one automatically on the next login."""

    iterations = 600_000
