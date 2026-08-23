from django.contrib import admin

from apps.engine.models import Assignment


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ["user_id", "experiment", "variant", "bucket", "assigned_at"]
    list_filter = ["experiment"]
    search_fields = ["user_id"]
    readonly_fields = ["user_id", "experiment", "version", "variant", "bucket", "context", "assigned_at"]
