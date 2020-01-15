from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.html import format_html

from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    ContentMetadata,
    EnterpriseCatalog,
)
from enterprise_catalog.apps.catalog.utils import get_content_filter_hash


@admin.register(ContentMetadata)
class ContentMetadataAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom ContentMetadata model. """
    list_display = ('id', 'content_key', 'content_type',)


class CatalogQueryForm(forms.ModelForm):
    class Meta:
        model = CatalogQuery
        fields = ('content_filter',)

    def clean_content_filter(self):
        content_filter = self.cleaned_data['content_filter']
        content_filter_hash = get_content_filter_hash(content_filter)
        if CatalogQuery.objects.filter(content_filter_hash=content_filter_hash).exists():
            raise ValidationError('Catalog Query with this Content filter already exists.')
        return content_filter


@admin.register(CatalogQuery)
class CatalogQueryAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom CatalogQuery model. """
    list_display = ('id',)
    form = CatalogQueryForm


@admin.register(EnterpriseCatalog)
class EnterpriseCatalogAdmin(admin.ModelAdmin):
    """ Admin configuration for the custom EnterpriseCatalog model. """
    list_display = ('uuid', 'enterprise_uuid', 'title', 'get_catalog_query',)

    def get_catalog_query(self, obj):
        link = reverse("admin:catalog_catalogquery_change", args=[obj.catalog_query.id])
        return format_html('<a href="{}">{}</a>', link, obj.catalog_query.content_filter_hash)

    get_catalog_query.short_description = 'Catalog Query'
