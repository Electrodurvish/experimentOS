import hashlib
import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.common.models import BaseModel


class User(AbstractUser, BaseModel):
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.email


class APIKey(BaseModel):
    key_prefix = models.CharField(max_length=16, db_index=True)
    hashed_key = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=255)
    project = models.ForeignKey(
        "organizations.Project",
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_api_keys",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "api_keys"

    def __str__(self):
        return f"{self.name} ({self.key_prefix}...)"

    @staticmethod
    def generate_key(environment="live"):
        """Generate a new API key. Returns (raw_key, prefix, hashed_key)."""
        raw = secrets.token_hex(32)
        prefix = f"xos_{environment}_"
        full_key = f"{prefix}{raw}"
        hashed = hashlib.sha256(full_key.encode()).hexdigest()
        return full_key, prefix, hashed
