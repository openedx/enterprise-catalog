import logging

from django.db import IntegrityError
from rest_framework import serializers

from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    EnterpriseCatalog,
)
from enterprise_catalog.apps.catalog.utils import get_content_filter_hash


logger = logging.getLogger(__name__)


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
            defaults={'content_filter': content_filter},
        )
        try:
            return EnterpriseCatalog.objects.create(**validated_data, catalog_query=catalog_query)
        except IntegrityError as exc:
            message = (
                'Encountered the following error in the create serializer: %s | '
                'content_filter: %s | '
                'catalog_query id: %s | '
                'validated_data: %s'
            )
            logger.error(message, (exc, content_filter, catalog_query.id, validated_data))
            raise

    def update(self, instance, validated_data):
        default_content_filter = None
        if instance.catalog_query:
            default_content_filter = instance.catalog_query.content_filter

        content_filter = validated_data.get('content_filter', default_content_filter)
        instance.catalog_query, _ = CatalogQuery.objects.get_or_create(
            content_filter_hash=get_content_filter_hash(content_filter),
            defaults={'content_filter': content_filter},
        )
        return super().update(instance, validated_data)


class EnterpriseCatalogCreateSerializer(EnterpriseCatalogSerializer):
    """
    Serializer for POST requests on the `EnterpriseCatalog` model

    UUID is writable to allow importing existing Enterprise Catalogs and keeping the same UUID
    """
    uuid = serializers.UUIDField(read_only=False, required=False)
