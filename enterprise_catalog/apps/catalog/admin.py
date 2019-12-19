from django.contrib import admin

from enterprise_catalog.apps.catalog.models import (
    CatalogContentKey,
    CatalogQuery,
    ContentMetadata,
    EnterpriseCatalog
)


class CatalogContentKeyAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom CatalogContentKey model. """
    list_display = ('catalog_query', 'content_key')


class EnterpriseCatalogAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom EnterpriseCatalog model. """
    list_display = ('enterprise_uuid', 'catalog_query')


class ContentMetadataAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom ContentMetadata model. """
    list_display = ('content_key', 'content_type')


admin.site.register(CatalogContentKey, CatalogContentKeyAdmin)
admin.site.register(CatalogQuery)
admin.site.register(ContentMetadata, ContentMetadataAdmin)
admin.site.register(EnterpriseCatalog, EnterpriseCatalogAdmin)
