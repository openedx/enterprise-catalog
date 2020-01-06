from rest_framework import serializers

from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    CatalogContentKey,
    EnterpriseCatalog
)


class QuerySerializerMixin:
    """
    Mixin for DRY query improvements. TBD if we need this or not

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


class CatalogQuerySerializer(QuerySerializerMixin, serializers.ModelSerializer):
    """
    Serializer for the `CatalogQuery` model
    """

    class Meta:
        model = CatalogQuery
        fields = ['id', 'title']

class CatalogContentKeySerializer(QuerySerializerMixin, serializers.ModelSerializer):
    """
    Serializer for the `CatalogContentKey` model
    """

    class Meta:
        model = CatalogContentKey
        fields = ['id']


class EnterpriseCatalogSerializer(QuerySerializerMixin, serializers.ModelSerializer):
    """
    Serializer for the `EnterpriseCatalog` model
    """
    enterprise_customer = serializers.UUIDField(source='enterprise_uuid')
    # content_filter = This is in the mgmt command WIP, but not sure if it should be part of this serializer
    enabled_course_modes = serializers.JSONField(write_only=True)
    publish_audit_enrollment_urls = serializers.BooleanField(write_only=True)

    class Meta:
        model = EnterpriseCatalog
        fields = ['uuid', 'title', 'enterprise_customer', 'enabled_course_modes', 'publish_audit_enrollment_urls']


class EnterpriseCatalogCreateSerializer(EnterpriseCatalogSerializer):
    """
    Serializer for POST requests on the `EnterpriseCatalog` model

    UUID is writable to allow importing existing Enterprise Catalogs and keeping the same UUID
    """
    uuid = serializers.UUIDField(read_only=False)
