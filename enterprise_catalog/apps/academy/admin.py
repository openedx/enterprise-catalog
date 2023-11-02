"""
Admin for academy models.
"""
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from enterprise_catalog.apps.academy.models import Academy, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """
    Django admin for Tag.
    """
    list_display = ('id', 'title', )
    search_fields = ('title', )


@admin.register(Academy)
class AcademyAdmin(SimpleHistoryAdmin):
    """
    Django admin for Academy.
    """
    list_display = ('uuid', 'title', 'created', 'modified', )
    search_fields = ('title', 'short_description', 'long_description', )
