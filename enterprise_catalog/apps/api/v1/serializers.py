from rest_framework import serializers

from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    EnterpriseCatalog,
)
from enterprise_catalog.apps.catalog.utils import get_content_filter_hash


class EnterpriseCatalogSerializer(serializers.ModelSerializer):
    """
    Serializer for the `EnterpriseCatalog` model
    """
    enterprise_customer = serializers.UUIDField(source='enterprise_uuid')
    enabled_course_modes = serializers.JSONField(write_only=True)
    publish_audit_enrollment_urls = serializers.BooleanField(write_only=True)
    content_filter = serializers.JSONField(write_only=True)

    class Meta:
        model = EnterpriseCatalog
        fields = [
            'uuid',
            'title',
            'enterprise_customer',
            'enabled_course_modes',
            'publish_audit_enrollment_urls',
            'content_filter',
        ]

    def create(self, validated_data):
        content_filter = validated_data.pop('content_filter')
        catalog_query, _ = CatalogQuery.objects.get_or_create(
            content_filter_hash=get_content_filter_hash(content_filter),
        )
        return EnterpriseCatalog.objects.create(**validated_data, catalog_query=catalog_query)


class EnterpriseCatalogCreateSerializer(EnterpriseCatalogSerializer):
    """
    Serializer for POST requests on the `EnterpriseCatalog` model

    UUID is writable to allow importing existing Enterprise Catalogs and keeping the same UUID
    """
    uuid = serializers.UUIDField(read_only=False, required=False)
