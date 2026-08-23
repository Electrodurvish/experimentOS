import hashlib

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.models import APIKey


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
        api_key.last_used_at = timezone.now()
        api_key.save(update_fields=["last_used_at"])

        return (None, api_key)

    def authenticate_header(self, request):
        return "X-API-Key"
