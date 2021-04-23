import logging

from django.db import IntegrityError
from rest_framework import serializers, status

from enterprise_catalog.apps.api.v1.utils import (
    get_enterprise_utm_context,
    is_any_course_run_active,
    update_query_parameters,
)
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    PROGRAM,
)
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    EnterpriseCatalog,
)
from enterprise_catalog.apps.catalog.utils import (
    get_content_filter_hash,
    get_parent_content_key,
)


logger = logging.getLogger(__name__)


def find_and_modify_catalog_query(content_filter, catalog_query_uuid=None):
    """
    This method aims to make sure UUID and content_filter in the catalog service
    match what Django Admin/passed in parameters have. We take the parameters as source of truth,
    but do not want to duplicate either UUID or content filter.

    Arguments:
        content_filter(dict): filter used to pick which courses are retrieved
        catalog_query_uuid(UUID/str): query uuid generated from LMS Django Admin.
            - If not provided, we should be receiving a "direct" content filter.
    Returns:
        a CatalogQuery object.
    """
    if catalog_query_uuid:
        catalog_query_from_uuid = CatalogQuery.get_by_uuid(uuid=catalog_query_uuid)
        if catalog_query_from_uuid:
            catalog_query_from_uuid.content_filter = content_filter
            catalog_query_from_uuid.content_filter_hash = get_content_filter_hash(content_filter)
            try:
                catalog_query_from_uuid.save()
            except IntegrityError as exc:
                raise serializers.ValidationError(
                    {'catalog_query': 'Content filter is not unique'},
                    code=status.HTTP_422_UNPROCESSABLE_ENTITY
                ) from exc
            return catalog_query_from_uuid
        else:
            content_filter_from_hash, _ = CatalogQuery.objects.update_or_create(
                content_filter_hash=get_content_filter_hash(content_filter),
                defaults={'content_filter': content_filter, 'uuid': catalog_query_uuid}
            )
            return content_filter_from_hash
    else:
        content_filter_from_hash, _ = CatalogQuery.objects.get_or_create(
            content_filter_hash=get_content_filter_hash(content_filter),
            defaults={'content_filter': content_filter}
        )

        return content_filter_from_hash


class EnterpriseCatalogSerializer(serializers.ModelSerializer):
    """
    Serializer for the `EnterpriseCatalog` model
    """
    enterprise_customer = serializers.UUIDField(source='enterprise_uuid')
    enterprise_customer_name = serializers.CharField(source='enterprise_name', write_only=True)
    enabled_course_modes = serializers.JSONField(write_only=True)
    publish_audit_enrollment_urls = serializers.BooleanField(write_only=True)
    content_filter = serializers.JSONField(write_only=True)
    catalog_query_uuid = serializers.UUIDField(required=False, allow_null=True)

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
            'catalog_query_uuid',
        ]

    def create(self, validated_data):
        content_filter = validated_data.pop('content_filter')
        catalog_query_uuid = validated_data.pop('catalog_query_uuid', None)
        catalog_query = find_and_modify_catalog_query(content_filter, catalog_query_uuid)
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

        return catalog

    def update(self, instance, validated_data):
        default_content_filter = None
        if instance.catalog_query:
            default_content_filter = instance.catalog_query.content_filter

        content_filter = validated_data.get('content_filter', default_content_filter)
        catalog_query_uuid = validated_data.pop('catalog_query_uuid', None)
        instance.catalog_query = find_and_modify_catalog_query(content_filter, catalog_query_uuid)

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
            dict: The modified json_metadata field.
        """
        enterprise_catalog = self.context['enterprise_catalog']
        content_type = instance.content_type
        json_metadata = instance.json_metadata.copy()
        marketing_url = json_metadata.get('marketing_url')
        content_key = json_metadata.get('key')
        parent_content_key = get_parent_content_key(json_metadata)

        if marketing_url:
            marketing_url = update_query_parameters(
                marketing_url,
                get_enterprise_utm_context(enterprise_catalog.enterprise_name)
            )
            json_metadata['marketing_url'] = marketing_url

        if content_type in (COURSE, COURSE_RUN):
            json_metadata['enrollment_url'] = enterprise_catalog.get_content_enrollment_url(
                content_resource=COURSE,
                content_key=content_key,
                parent_content_key=parent_content_key,
            )
            json_metadata['xapi_activity_id'] = enterprise_catalog.get_xapi_activity_id(
                content_resource=content_type,
                content_key=content_key,
            )
            if content_type == COURSE:
                course_runs = json_metadata.get('course_runs', [])
                json_metadata['active'] = is_any_course_run_active(course_runs)
                for course_run in course_runs:
                    course_run['enrollment_url'] = enterprise_catalog.get_content_enrollment_url(
                        content_resource=COURSE,
                        content_key=course_run.get('key'),
                        parent_content_key=content_key,
                    )
        elif content_type == PROGRAM:
            # This URL will always be blank because json_metadata['key'] doesn't exist for programs
            json_metadata['enrollment_url'] = enterprise_catalog.get_content_enrollment_url(
                content_resource=PROGRAM,
                content_key=content_key,
                parent_content_key=parent_content_key,
            )

        return json_metadata
