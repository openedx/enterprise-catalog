from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from enterprise_catalog.apps.curation import models


class EnterpriseCurationConfigAdmin(SimpleHistoryAdmin):
    """ Admin configuration for the EnterpriseCurationConfig model. """
    list_display = (
        'uuid',
        'enterprise_uuid',
        'title',
        'is_highlight_feature_active',
    )
    search_fields = (
        'uuid',
        'enterprise_uuid',
    )


class HighlightSetAdmin(SimpleHistoryAdmin):
    """ Admin config for HighlightSet model. """
    list_display = (
        'uuid',
        'title',
        'enterprise_curation',
        'is_published',
    )
    search_fields = (
        'uuid',
        'enterprise_uuid',
        'enterprise_curation',
    )


class HighlightedContentAdmin(SimpleHistoryAdmin):
    """ Admin config for HighlightedContent model. """
    list_display = (
        'uuid',
        'catalog_highlight_set',
        'content_metadata',
    )
    search_fields = (
        'uuid',
        'catalog_highlight_set',
        'content_metadata',
    )


admin.site.register(models.EnterpriseCurationConfig, EnterpriseCurationConfigAdmin)
admin.site.register(models.HighlightSet, HighlightSetAdmin)
admin.site.register(models.HighlightedContent, HighlightedContentAdmin)
