from django.contrib import admin

from apps.experiments.models import Experiment, ExperimentVersion, TargetingRule, Variant


class VariantInline(admin.TabularInline):
    model = Variant
    extra = 0


class TargetingRuleInline(admin.StackedInline):
    model = TargetingRule
    extra = 0
    max_num = 1


@admin.register(Experiment)
class ExperimentAdmin(admin.ModelAdmin):
    list_display = ["key", "name", "status", "project", "owner", "created_at"]
    list_filter = ["status", "experiment_type", "project"]
    search_fields = ["key", "name"]
    readonly_fields = ["started_at", "ended_at"]


@admin.register(ExperimentVersion)
class ExperimentVersionAdmin(admin.ModelAdmin):
    list_display = ["experiment", "version_number", "traffic_allocation", "is_active", "is_locked"]
    list_filter = ["is_active", "is_locked"]
    inlines = [VariantInline, TargetingRuleInline]
