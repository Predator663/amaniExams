from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ExpiringTokenAuthentication(TokenAuthentication):
    """The normal login token, but it stops working TOKEN_TTL_HOURS after the login (default 12). A stolen or leaked token
    is therefore useful for hours, not forever. The expired token is deleted; the app sends her back to the login screen."""

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        ttl = float(getattr(settings, "TOKEN_TTL_HOURS", 0) or 0)
        if ttl and token.created < timezone.now() - timedelta(hours=ttl):
            token.delete()
            raise AuthenticationFailed("Your session has expired. Please log in again.")
        return user, token
