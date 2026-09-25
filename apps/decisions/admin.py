from django.contrib import admin

from apps.decisions.models import Decision, Guardrail, RolloutChange, RolloutPolicy


@admin.register(Guardrail)
class GuardrailAdmin(admin.ModelAdmin):
    list_display = ["name", "experiment", "metric_name", "operator", "threshold", "action", "is_active"]
    list_filter = ["source", "action", "is_active"]


@admin.register(RolloutPolicy)
class RolloutPolicyAdmin(admin.ModelAdmin):
    list_display = ["experiment", "auto_advance", "auto_rollback", "rollback_percentage", "min_health_score"]


@admin.register(Decision)
class DecisionAdmin(admin.ModelAdmin):
    list_display = ["experiment", "recommendation", "confidence_label", "applied_action", "triggered_by", "created_at"]
    list_filter = ["recommendation", "triggered_by"]
    readonly_fields = [f.name for f in Decision._meta.fields]


@admin.register(RolloutChange)
class RolloutChangeAdmin(admin.ModelAdmin):
    list_display = ["experiment", "action", "from_percentage", "to_percentage", "automated", "created_at"]
    list_filter = ["action", "automated"]
