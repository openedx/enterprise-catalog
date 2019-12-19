from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from enterprise_catalog.apps.catalog.models import (
    CatalogContentKey,
    CatalogQuery,
    ContentMetadata,
    EnterpriseCatalog,
)


@admin.register(CatalogContentKey)
class CatalogContentKeyAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom CatalogContentKey model. """
    list_display = ('id', 'get_catalog_query', 'get_content_key',)

    def get_catalog_query(self, obj):
        link = reverse("admin:catalog_catalogquery_change", args=[obj.catalog_query.id])
        return format_html('<a href="{}">{}</a>', link, obj.catalog_query.title)
    
    def get_content_key(self, obj):
        link = reverse("admin:catalog_contentmetadata_change", args=[obj.content_key.id])
        return format_html('<a href="{}">{}</a>', link, obj.content_key.content_key)

    get_catalog_query.short_description = 'Catalog Query'
    get_content_key.short_description = 'Content Key'


@admin.register(ContentMetadata)
class ContentMetadataAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom ContentMetadata model. """
    list_display = ('id', 'content_key', 'content_type',)


@admin.register(CatalogQuery)
class CatalogQueryAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom CatalogQuery model. """
    list_display = ('id', 'title',)


@admin.register(EnterpriseCatalog)
class EnterpriseCatalogAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom EnterpriseCatalog model. """
    list_display = ('uuid', 'enterprise_uuid', 'title', 'get_catalog_query',)

    def get_catalog_query(self, obj):
        link = reverse("admin:catalog_catalogquery_change", args=[obj.catalog_query.id])
        return format_html('<a href="{}">{}</a>', link, obj.catalog_query.title)

    get_catalog_query.short_description = 'Catalog Query'
