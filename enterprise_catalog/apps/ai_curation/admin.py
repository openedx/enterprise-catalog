"""
Admin for AI Curation
"""
from django.contrib import admin

from enterprise_catalog.apps.ai_curation.models import AICurationTask


@admin.register(AICurationTask)
class AICurationTaskAdmin(admin.ModelAdmin):
    """
    Admin configuration for the custom AICurationTask model.
    """
    list_display = (
        'task_id',
        'status',
        'created',
        'modified',
    )
    list_filter = (
        'status',
    )
    search_fields = (
        'task_id',
    )
    ordering = (
        '-created',
    )

    def has_add_permission(self, request, obj=None):  # pylint: disable=unused-argument
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
