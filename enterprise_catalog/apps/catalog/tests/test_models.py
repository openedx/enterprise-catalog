""" Tests for catalog models. """

from collections import OrderedDict
from unittest import mock

from django.test import TestCase, override_settings

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    PROGRAM,
)
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    update_contentmetadata_from_discovery,
)
from enterprise_catalog.apps.catalog.tests import factories


class TestModels(TestCase):
    """ Models tests. """

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @mock.patch('enterprise_catalog.apps.api_client.discovery_cache.DiscoveryApiClient')
    def test_contentmetadata_update_from_discovery(self, mock_client):
        """
        update_contentmetadata_from_discovery should update or create
        ContentMetadata Objects from the discovery service api call/
        """
        course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+testX'),
            ('key', 'edX+testX'),
            ('title', 'test course'),
        ])
        course_run_metadata = OrderedDict([
            ('aggregation_key', 'courserun:edX+testX'),
            ('key', 'course-v1:edX+testX+1'),
            ('title', 'test course run'),
        ])
        program_metadata = OrderedDict([
            ('aggregation_key', 'program:fake-uuid'),
            ('title', 'test program'),
            ('uuid', 'fake-uuid'),
        ])
        mock_client.return_value.get_metadata_by_query.return_value = [
            course_metadata,
            course_run_metadata,
            program_metadata,
        ]
        catalog = factories.EnterpriseCatalogFactory()

        self.assertEqual(ContentMetadata.objects.count(), 0)
        update_contentmetadata_from_discovery(catalog.catalog_query)
        mock_client.assert_called_once()
        self.assertEqual(ContentMetadata.objects.count(), 3)

        associated_metadata = catalog.content_metadata

        # Assert stored content metadata is correct for each type
        course_cm = ContentMetadata.objects.get(content_key=course_metadata['key'])
        self.assertEqual(course_cm.content_type, COURSE)
        self.assertEqual(course_cm.parent_content_key, None)
        self.assertEqual(course_cm.json_metadata, course_metadata)
        assert course_cm in associated_metadata

        course_run_cm = ContentMetadata.objects.get(content_key=course_run_metadata['key'])
        self.assertEqual(course_run_cm.content_type, COURSE_RUN)
        self.assertEqual(course_run_cm.parent_content_key, course_metadata['key'])
        self.assertEqual(course_run_cm.json_metadata, course_run_metadata)
        assert course_run_cm in associated_metadata

        program_cm = ContentMetadata.objects.get(content_key=program_metadata['uuid'])
        self.assertEqual(program_cm.content_type, PROGRAM)
        self.assertEqual(program_cm.parent_content_key, None)
        self.assertEqual(program_cm.json_metadata, program_metadata)
        assert program_cm in associated_metadata

        # Run again and expect that we will unassociate some content metadata
        # from catalog query while perserving the content metadata objects
        # themselves.
        mock_client.return_value.get_metadata_by_query.return_value = [program_metadata]
        update_contentmetadata_from_discovery(catalog.catalog_query)
        self.assertEqual(ContentMetadata.objects.count(), 3)

        associated_metadata = catalog.content_metadata
        assert course_cm not in associated_metadata
        assert course_run_cm not in associated_metadata
        assert program_cm in associated_metadata
