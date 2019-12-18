from django.contrib import admin

from enterprise_catalog.apps.catalog.models import CatalogQuery, EnterpriseCatalog


class EnterpriseCatalogAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom EnterpriseCatalog model. """
    list_display = ('enterprise_uuid', 'catalog_query')


admin.site.register(CatalogQuery)
admin.site.register(EnterpriseCatalog, EnterpriseCatalogAdmin)
