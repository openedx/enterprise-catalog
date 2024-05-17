import logging
from re import search

from django.db import IntegrityError, models
from rest_framework import serializers, status

from enterprise_catalog.apps.academy.models import Academy, Tag
from enterprise_catalog.apps.api.v1.utils import (
    get_archived_content_count,
    get_enterprise_utm_context,
    get_most_recent_modified_time,
    is_any_course_run_active,
    update_query_parameters,
)
from enterprise_catalog.apps.catalog.algolia_utils import (
    get_initialized_algolia_client,
)
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    PROGRAM,
)
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    ContentMetadata,
    EnterpriseCatalog,
)
from enterprise_catalog.apps.catalog.utils import get_content_filter_hash
from enterprise_catalog.apps.curation.models import (
    EnterpriseCurationConfig,
    HighlightedContent,
    HighlightSet,
)


logger = logging.getLogger(__name__)


def find_and_modify_catalog_query(
        content_filter, catalog_query_uuid=None, query_title=None,
):
    """
    This method aims to make sure UUID, query title and content_filter in the catalog service
    match what Django Admin/passed in parameters have. We take the parameters as source of truth,
    but do not want to duplicate UUID, title or content filter.

    Arguments:
        content_filter(dict): filter used to pick which courses are retrieved
        catalog_query_uuid(UUID/str): query uuid generated from LMS Django Admin.
            - If not provided, we should be receiving a "direct" content filter.
        query_title(str): query title created in LMS Django Admin.
            - Can be null.
    Returns:
        a CatalogQuery object.
    """
    hashed_content_filter = get_content_filter_hash(content_filter)
    if catalog_query_uuid:
        catalog_query_from_uuid = CatalogQuery.get_by_uuid(uuid=catalog_query_uuid)
        if catalog_query_from_uuid:
            catalog_query_from_uuid.content_filter = content_filter
            catalog_query_from_uuid.title = query_title
            catalog_query_from_uuid.content_filter_hash = hashed_content_filter
            try:
                catalog_query_from_uuid.save()
            except IntegrityError as exc:
                column = search("(?<=for key ')(.*)(?=')", str(exc))
                logger.exception(f'Error occurred while saving catalog query: {exc}')  # pylint:disable=logging-fstring-interpolation
                raise serializers.ValidationError(
                    {'catalog_query': f'{column} is not unique'},
                    code=status.HTTP_422_UNPROCESSABLE_ENTITY
                ) from exc
            return catalog_query_from_uuid
        else:
            content_filter_from_hash, _ = CatalogQuery.objects.update_or_create(
                content_filter_hash=hashed_content_filter,
                defaults={'content_filter': content_filter, 'uuid': catalog_query_uuid, 'title': query_title}
            )
            return content_filter_from_hash
    else:
        content_filter_from_hash, _ = CatalogQuery.objects.get_or_create(
            content_filter_hash=hashed_content_filter,
            defaults={'content_filter': content_filter, 'title': query_title}
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
    catalog_modified = serializers.DateTimeField(source='modified', required=False)
    content_last_modified = serializers.SerializerMethodField()
    query_title = serializers.CharField(allow_null=True, required=False)

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
            'content_last_modified',
            'catalog_modified',
            'query_title',
        ]

    def get_content_last_modified(self, obj):
        return obj.content_metadata.aggregate(models.Max('modified')).get('modified__max')

    def create(self, validated_data):
        content_filter = validated_data.pop('content_filter')
        catalog_query_uuid = validated_data.pop('catalog_query_uuid', None)
        query_title = validated_data.pop('query_title', None)

        catalog_query = find_and_modify_catalog_query(
            content_filter,
            catalog_query_uuid,
            query_title,
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

        return catalog

    def update(self, instance, validated_data):
        default_content_filter = None
        default_query_title = None
        default_query_uuid = None
        if instance.catalog_query:
            default_content_filter = instance.catalog_query.content_filter
            default_query_title = instance.catalog_query.title if hasattr(instance.catalog_query, 'title') else None
            default_query_uuid = str(instance.catalog_query.uuid)

        content_filter = validated_data.get('content_filter', default_content_filter)
        query_title = validated_data.get('query_title', default_query_title)
        catalog_query_uuid = validated_data.pop('catalog_query_uuid', default_query_uuid)
        instance.catalog_query = find_and_modify_catalog_query(
            content_filter,
            catalog_query_uuid,
            query_title,
        )
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
        catalog_modified = None
        customer_modified = None
        enterprise_catalog = self.context.get('enterprise_catalog')

        if enterprise_catalog:
            catalog_modified = enterprise_catalog.modified
        if enterprise_catalog and not self.context.get('skip_customer_fetch'):
            customer_modified = enterprise_catalog.enterprise_customer.last_modified_date

        content_type = instance.content_type
        json_metadata = instance.json_metadata.copy()
        marketing_url = json_metadata.get('marketing_url')
        content_key = json_metadata.get('key')

        # Currently (3/17/23) product source can potentially be two different formats, string and dict.
        # For the purposes of the metadata serializer, we will standardize and default to the dict format.
        if product_source := json_metadata.get('product_source'):
            if isinstance(product_source, str):
                json_metadata['product_source'] = {'name': product_source, 'slug': None, 'description': None}

        # The enrollment URL field of content metadata is generated on request and is determined by the status of the
        # enterprise customer as well as the catalog. So, in order to detect when content metadata has last been
        # modified, we have to also check the customer and the catalog's modified times.
        modified_time = get_most_recent_modified_time(
            instance.modified,
            catalog_modified,
            customer_modified
        )

        json_metadata['content_last_modified'] = modified_time

        if marketing_url and enterprise_catalog:
            marketing_url = update_query_parameters(
                marketing_url,
                get_enterprise_utm_context(enterprise_catalog.enterprise_name)
            )
            json_metadata['marketing_url'] = marketing_url

        if content_type in (COURSE, COURSE_RUN):
            if enterprise_catalog:
                json_metadata['enrollment_url'] = None
                if not self.context.get('skip_customer_fetch'):
                    json_metadata['enrollment_url'] = enterprise_catalog.get_content_enrollment_url(instance)
                json_metadata['xapi_activity_id'] = enterprise_catalog.get_xapi_activity_id(
                    content_resource=content_type,
                    content_key=content_key,
                )
            if content_type == COURSE:
                serialized_course_runs = json_metadata.get('course_runs', [])
                json_metadata['active'] = is_any_course_run_active(serialized_course_runs)
                # We don't include enrollment_url values for the nested course runs in a course
                # for exec-ed-2u content, because enrollment fulfillment for such content
                # is controlled via Entitlements, which are tied directly to Courses
                # (as opposed to Seats, which are tied to Course Runs).
                if not instance.is_exec_ed_2u_course and not self.context.get('skip_customer_fetch'):
                    self._add_course_run_enrollment_urls(instance, serialized_course_runs)
        elif content_type == PROGRAM:
            # We want this to be null, because we have no notion
            # of directly enrolling in a program.
            json_metadata['enrollment_url'] = None

        return json_metadata

    def _add_course_run_enrollment_urls(self, course_instance, serialized_course_runs):
        """
        For the given `course_instance`, computes the enrollment url for each
        child course run and adds it to the serialized representation of the
        course run record in `serialized_course_runs`.
        """
        # Early guard in case the context has no catalog
        if not self.context.get('enterprise_catalog'):
            return

        urls_by_course_run_key = {}
        for course_run in ContentMetadata.get_child_records(course_instance):
            urls_by_course_run_key[course_run.content_key] = \
                self.context['enterprise_catalog'].get_content_enrollment_url(course_run)

        for serialized_run in serialized_course_runs:
            serialized_run['enrollment_url'] = urls_by_course_run_key.get(serialized_run['key'])


class HighlightedContentSerializer(serializers.ModelSerializer):
    """
    Serializer for the `HighlightedContent` model.
    """
    aggregation_key = serializers.SerializerMethodField()

    class Meta:
        model = HighlightedContent
        fields = [
            'uuid',
            'aggregation_key',
            'content_type',
            'content_key',
            'title',
            'card_image_url',
            'authoring_organizations',
            'course_run_statuses',
        ]

    def get_aggregation_key(self, obj):
        """
        Returns the aggregation key for the associated ContentMetadata.
        """
        return obj.aggregation_key


class HighlightSetSerializer(serializers.ModelSerializer):
    """
    Serializer for the `HighlightSet` model.
    """
    title = serializers.CharField()
    is_published = serializers.BooleanField(required=False)
    highlighted_content = serializers.SerializerMethodField()

    class Meta:
        model = HighlightSet
        fields = [
            'uuid',
            'title',
            'is_published',
            'enterprise_curation',
            'card_image_url',
            'highlighted_content',
        ]

    def get_highlighted_content(self, obj):
        """
        Returns the data for the associated content included in this HighlightSet object.
        """
        qs = obj.highlighted_content.order_by('created').select_related('content_metadata')
        return HighlightedContentSerializer(qs, many=True).data


class EnterpriseCurationConfigSerializer(serializers.ModelSerializer):
    """
    Serializer for the `EnterpriseCurationConfig` model.
    """
    enterprise_customer = serializers.UUIDField(source='enterprise_uuid')
    title = serializers.CharField()
    is_highlight_feature_active = serializers.BooleanField(required=False)
    can_only_view_highlight_sets = serializers.BooleanField(required=False)
    highlight_sets = serializers.SerializerMethodField()

    class Meta:
        model = EnterpriseCurationConfig
        fields = [
            'uuid',
            'created',
            'modified',
            'enterprise_customer',
            'title',
            'is_highlight_feature_active',
            'can_only_view_highlight_sets',
            'highlight_sets',
        ]

    def get_highlight_sets(self, obj):
        """
        Returns minimal information around the HighlightSets that exist for the EnterpriseCurationConfig.

        Notes:
        * Highlighted content UUIDs are sorted by the order in which they were added by the enterprise admin.
          This may help inform frontend code determine which order to display content.
        """
        catalog_highlight_sets = obj.catalog_highlights.all().order_by('-created')
        return [
            {
                'uuid': highlight_set.uuid,
                'is_published': highlight_set.is_published,
                'title': highlight_set.title,
                'card_image_url': highlight_set.card_image_url,
                'highlighted_content_uuids': [
                    item.uuid for item in highlight_set.highlighted_content.order_by('created')
                ],
                'archived_content_count': get_archived_content_count(highlight_set.highlighted_content.all()),
            }
            for highlight_set in catalog_highlight_sets
        ]


class AcademyTagsListSerializer(serializers.ListSerializer):  # pylint: disable=abstract-method
    """
    List serializer for filtering academy tags with no index hits.
    """

    def to_representation(self, obj):  # pylint: disable=arguments-renamed
        """Filter academy tags with no index hits. """
        tags = super().to_representation(obj)
        algolia_client = get_initialized_algolia_client()
        academy_uuid = self.context.get('academy_uuid')
        enterprise_uuid = self.context.get('enterprise_uuid')
        if academy_uuid and enterprise_uuid:
            search_query = {
                'filters': f'academy_uuids:{academy_uuid} AND enterprise_customer_uuids:{enterprise_uuid}',
                'maxFacetHits': 50
            }
        else:
            search_query = {'maxFacetHits': 50}
        response = algolia_client.algolia_index.search_for_facet_values('academy_tags', '', search_query)
        tag_titles_with_results = []
        for hit in response.get('facetHits', []):
            if hit.get('count') > 0:
                tag_titles_with_results.append(hit.get('value'))
        tags_with_results = []
        for tag in tags:
            tag_title = tag['title']
            if tag_title in tag_titles_with_results:
                tags_with_results.append(tag)
        return tags_with_results


class TagsSerializer(serializers.ModelSerializer):
    """
    Serializer for the `Tag` model.
    """
    class Meta:
        model = Tag
        fields = ['id', 'title', 'description']
        list_serializer_class = AcademyTagsListSerializer


class AcademySerializer(serializers.ModelSerializer):
    """
    Serializer for the `Academy` model.
    """
    tags = serializers.SerializerMethodField('get_tags_serializer')

    class Meta:
        model = Academy
        fields = ['uuid', 'title', 'short_description', 'long_description', 'image', 'tags']
        lookup_field = 'uuid'

    def get_tags_serializer(self, obj):
        academy_uuid = self.context.get('academy_uuid')
        serializer_context = {'academy_uuid': academy_uuid}
        tags = obj.tags.all()
        serializer = TagsSerializer(tags, many=True, context=serializer_context)
        return serializer.data
