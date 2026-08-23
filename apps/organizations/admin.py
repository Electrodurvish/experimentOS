from django.contrib import admin

from apps.organizations.models import Organization, Project


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "created_at"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "organization", "created_at"]
    list_filter = ["organization"]
    prepopulated_fields = {"slug": ("name",)}
