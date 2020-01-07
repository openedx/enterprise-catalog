from rest_framework import serializers

from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


class EnterpriseCatalogSerializer(serializers.ModelSerializer):
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
