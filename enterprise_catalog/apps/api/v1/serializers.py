import copy
import logging

from django.db import IntegrityError
from rest_framework import serializers

from enterprise_catalog.apps.api.tasks import update_catalog_metadata_task
from enterprise_catalog.apps.api.v1.utils import (
    get_enterprise_utm_context,
    is_any_course_run_enrollable,
    update_query_parameters,
)
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
    enterprise_customer_name = serializers.CharField(source='enterprise_name', write_only=True)
    enabled_course_modes = serializers.JSONField(write_only=True)
    publish_audit_enrollment_urls = serializers.BooleanField(write_only=True)
    content_filter = serializers.JSONField(write_only=True)

    class Meta:
        model = EnterpriseCatalog
        fields = [
            'uuid',
            'title',
            'enterprise_customer',
            'enterprise_customer_name',
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
            catalog = EnterpriseCatalog.objects.create(
                **validated_data,
                catalog_query=catalog_query
            )
        except IntegrityError as exc:
            message = (
                'Encountered the following error in the create serializer: %s | '
                'content_filter: %s | '
                'catalog_query id: %s | '
                'validated_data: %s'
            )
            logger.error(message, exc, content_filter, catalog_query.id, validated_data)
            raise

        message = (
            'Spinning off update_catalog_metadata_task from create serializer '
            'to update content_metadata for catalog %s'
        )
        logger.info(message, catalog)
        update_catalog_metadata_task.delay(catalog_uuid=str(catalog.uuid))

        return catalog

    def update(self, instance, validated_data):
        default_content_filter = None
        if instance.catalog_query:
            default_content_filter = instance.catalog_query.content_filter

        content_filter = validated_data.get('content_filter', default_content_filter)
        instance.catalog_query, _ = CatalogQuery.objects.get_or_create(
            content_filter_hash=get_content_filter_hash(content_filter),
            defaults={'content_filter': content_filter},
        )

        message = (
            'Spinning off update_catalog_metadata_task from update serializer '
            'to update content_metadata for catalog %s'
        )
        logger.info(message, instance)
        update_catalog_metadata_task.delay(catalog_uuid=str(instance.uuid))

        return super().update(instance, validated_data)


class EnterpriseCatalogCreateSerializer(EnterpriseCatalogSerializer):
    """
    Serializer for POST requests on the `EnterpriseCatalog` model

    UUID is writable to allow importing existing Enterprise Catalogs and keeping the same UUID
    """
    uuid = serializers.UUIDField(read_only=False, required=False)


class ImmutableStateSerializer(serializers.Serializer):
    """
    Base serializer for any serializer that inhibits state changing requests.
    """

    def create(self, validated_data):
        """
        Do not perform any operations for state changing requests.
        """

    def update(self, instance, validated_data):
        """
        Do not perform any operations for state changing requests.
        """


class ContentMetadataSerializer(ImmutableStateSerializer):
    """
    Serializer for rendering Content Metadata objects
    """

    def to_representation(self, instance):
        """
        Return the updated content metadata dictionary.

        Arguments:
            instance (dict): ContentMetadata instance.

        Returns:
            dict: The updated ContentMetadata object.
        """
        updated_metadata = copy.deepcopy(instance)
        enterprise_catalog = self.context['enterprise_catalog']
        content_type = updated_metadata.content_type
        json_metadata = updated_metadata.json_metadata
        marketing_url = json_metadata.get('marketing_url')
        content_key = json_metadata.get('key')

        if marketing_url:
            marketing_url = update_query_parameters(
                marketing_url,
                get_enterprise_utm_context(enterprise_catalog.enterprise_name)
            )
            json_metadata['marketing_url'] = marketing_url

        if content_type in ('course', 'courserun'):
            json_metadata['enrollment_url'] = enterprise_catalog.get_content_enrollment_url(
                content_resource='course',
                content_key=content_key,
            )
            if content_type == 'course':
                course_runs = json_metadata.get('course_runs', [])
                json_metadata['active'] = is_any_course_run_enrollable(course_runs)
                for course_run in course_runs:
                    course_run['enrollment_url'] = enterprise_catalog.get_content_enrollment_url(
                        content_resource='course',
                        content_key=content_key,
                    )
        elif content_type == 'program':
            json_metadata['enrollment_url'] = enterprise_catalog.get_content_enrollment_url(
                content_resource='program',
                content_key=content_key,
            )

        return updated_metadata
