"""Admin registrations for demo models."""

from oldman.apps.admin import ModelAdmin


class DemoProjectAdmin(ModelAdmin):
    """Admin presentation for demo projects."""

    require_superuser = True
    list_display = ("id", "name", "owner", "status", "is_active", "created_at")
    search_fields = ("name", "owner", "status")
    readonly_fields = ("created_at",)
    ordering = ("name",)
