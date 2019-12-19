from rest_framework import serializers

from enterprise_catalog.apps.catalog.models import CatalogQuery, EnterpriseCatalog


class QuerySerializerMixin:
    """
    Mixin for DRY query improvements

    Used by inheriting from the mixin and declaring the `related_fields` and `prefetch_fields` specific to the model
    on your serializer, and then calling `get_related_queries` when getting the queryset in your view.

    Adapted from https://riptutorial.com/django-rest-framework/example/7832/speed-up-serializers-queries
    """
    related_fields = []  # For selecting a single object (i.e. OneToOne or ForeignKey)
    prefetch_fields = []  # For selecting a group of objects (i.e. ManyToMany, reverse ForeignKeys, etc.)

    @classmethod
    def get_related_queries(cls, queryset):
        if cls.related_fields:
            queryset = queryset.select_related(*cls.related_fields)
        if cls.prefetch_fields:
            queryset = queryset.prefetch_related(*cls.prefetch_fields)

        return queryset


class CatalogQuerySerializer(serializers.ModelSerializer):
    """
    Serializer for the `CatalogQueryModel`
    """
    class Meta:
        model = CatalogQuery
        fields = ['title', 'content_filter']


class EnterpriseCatalogSerializer(serializers.ModelSerializer):
    """
    Serializer for the `EnterpriseCatalogModel`
    """
    related_fields = ['catalog_query']
    catalog_query = CatalogQuerySerializer()

    class Meta:
        model = EnterpriseCatalog
        fields = ['uuid', 'enterprise_uuid', 'catalog_query']
