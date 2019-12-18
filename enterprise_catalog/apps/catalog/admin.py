from django.contrib import admin

from enterprise_catalog.apps.catalog.models import CatalogContentKey, CatalogQuery, EnterpriseCatalog


class CatalogContentKeyAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom CatalogContentKey model. """
    list_display = ('catalog_query', 'content_key')


class EnterpriseCatalogAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom EnterpriseCatalog model. """
    list_display = ('enterprise_uuid', 'catalog_query')


admin.site.register(CatalogContentKey, CatalogContentKeyAdmin)
admin.site.register(CatalogQuery)
admin.site.register(EnterpriseCatalog, EnterpriseCatalogAdmin)
