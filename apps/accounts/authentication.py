import hashlib
from datetime import timedelta

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.models import APIKey

LAST_USED_RESOLUTION = timedelta(minutes=1)


class APIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        key = request.headers.get("X-API-Key")
        if not key:
            return None

        hashed = hashlib.sha256(key.encode()).hexdigest()

        try:
            api_key = APIKey.objects.select_related("project").get(
                hashed_key=hashed,
                is_active=True,
            )
        except APIKey.DoesNotExist:
            raise AuthenticationFailed("Invalid API key.")

        if api_key.expires_at and api_key.expires_at < timezone.now():
            raise AuthenticationFailed("API key has expired.")

        request.project = api_key.project
        now = timezone.now()
        # Avoid a write on every SDK request: last_used_at is only needed to minute precision.
        if api_key.last_used_at is None or now - api_key.last_used_at > LAST_USED_RESOLUTION:
            APIKey.objects.filter(pk=api_key.pk).update(last_used_at=now)
            api_key.last_used_at = now

        return (None, api_key)

    def authenticate_header(self, request):
        return "X-API-Key"
