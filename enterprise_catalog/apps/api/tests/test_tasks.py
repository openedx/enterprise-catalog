"""
Tests for the enterprise_catalog API celery tasks
"""
from unittest import mock

from django.test import TestCase

from enterprise_catalog.apps.api import tasks
from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.models import ContentMetadata
from enterprise_catalog.apps.catalog.tests.factories import (
    CatalogQueryFactory,
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
)


class EnterpriseCatalogCeleryTaskTests(TestCase):
    @mock.patch('enterprise_catalog.apps.api.tasks.update_contentmetadata_from_discovery')
    def test_refresh_metadata(self, update_contentmetadata_from_discovery_mock):
        """
        Assert update_catalog_metadata_task is called with correct catalog_query_id
        """
        catalog_query = CatalogQueryFactory()
        tasks.update_catalog_metadata_task(catalog_query.id)
        update_contentmetadata_from_discovery_mock.assert_called_with(catalog_query.id)

    @mock.patch('enterprise_catalog.apps.api_client.discovery.OAuthAPIClient')
    def test_update_full_metadata(self, mock_oauth_client):
        """
        Assert that full course metadata is merged with original json_metadata for all ContentMetadata records.
        """
        course_data_1 = {'key': 'fakeX', 'full_course_only_field': 'test_1'}
        course_data_2 = {'key': 'testX', 'full_course_only_field': 'test_2'}

        mock_oauth_client.return_value.get.return_value.json.return_value = {
            'results': [course_data_1, course_data_2],
        }

        enterprise_catalog = EnterpriseCatalogFactory()
        catalog_query = enterprise_catalog.catalog_query

        metadata_1 = ContentMetadataFactory(content_type=COURSE, content_key='fakeX')
        metadata_1.catalog_queries.set([catalog_query])
        metadata_2 = ContentMetadataFactory(content_type=COURSE, content_key='testX')
        metadata_2.catalog_queries.set([catalog_query])

        assert metadata_1.json_metadata != course_data_1
        assert metadata_2.json_metadata != course_data_2

        tasks.update_full_content_metadata_task()

        metadata_1 = ContentMetadata.objects.get(content_key='fakeX')
        metadata_2 = ContentMetadata.objects.get(content_key='testX')

        # add aggregation_key and uuid to course objects since they should now exist
        # after merging the original json_metadata with the course metadata
        course_data_1.update({
            'uuid': metadata_1.json_metadata.get('uuid'),
            'aggregation_key': 'course:fakeX',
        })
        course_data_2.update({
            'uuid': metadata_2.json_metadata.get('uuid'),
            'aggregation_key': 'course:testX',
        })

        assert metadata_1.json_metadata == course_data_1
        assert metadata_2.json_metadata == course_data_2

    @mock.patch('enterprise_catalog.apps.api.tasks.AlgoliaSearchClient')
    def test_index_algolia(self, mock_search_client):
        ALGOLIA_FIELDS = ['key', 'objectID', 'enterprise_customer_uuids', 'enterprise_catalog_uuids']

        enterprise_catalog = EnterpriseCatalogFactory()
        catalog_query = enterprise_catalog.catalog_query
        metadata = ContentMetadataFactory(content_type=COURSE, content_key='fakeX')
        metadata.catalog_queries.set([catalog_query])

        tasks.index_enterprise_catalog_courses_in_algolia_task(ALGOLIA_FIELDS, content_keys=['fakeX'])

        mock_search_client.return_value.init_index.assert_called_once_with()

        algolia_objects = []
        algolia_objects.append({
            'key': metadata.content_key,
            'objectID': 'course-{}'.format(metadata.json_metadata.get('uuid')),
            'enterprise_customer_uuids': [str(enterprise_catalog.enterprise_uuid)],
            'enterprise_catalog_uuids': [str(enterprise_catalog.uuid)],
        })
        mock_search_client.return_value.partially_update_index.assert_called_once_with(algolia_objects)
