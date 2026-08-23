from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import APIKey, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "username", "first_name", "last_name", "is_staff", "created_at"]
    ordering = ["-created_at"]


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ["name", "key_prefix", "project", "is_active", "created_at", "last_used_at"]
    list_filter = ["is_active"]
    readonly_fields = ["key_prefix", "hashed_key", "created_at"]
