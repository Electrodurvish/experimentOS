from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["experiment", "actor", "action", "created_at"]
    list_filter = ["action"]
    search_fields = ["experiment__key"]
    readonly_fields = [
        "experiment", "actor", "action", "old_value",
        "new_value", "metadata", "ip_address", "created_at",
    ]
