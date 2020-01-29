""" Tests for catalog models. """

from collections import OrderedDict

import mock
from django.test import TestCase

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

    @mock.patch('enterprise_catalog.apps.catalog.models.DiscoveryApiClient')
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
        mock_client.return_value.get_metadata_by_query.return_value = {
            'count': 3,
            'previous': None,
            'next': None,
            'results': [course_metadata, course_run_metadata, program_metadata],
        }
        catalog = factories.EnterpriseCatalogFactory()

        self.assertEqual(ContentMetadata.objects.count(), 0)
        update_contentmetadata_from_discovery(catalog.uuid)
        mock_client.assert_called_once()
        self.assertEqual(ContentMetadata.objects.count(), 3)

        # Assert stored content metadata is correct for each type
        course_cm = ContentMetadata.objects.get(content_key=course_metadata['key'])
        self.assertEqual(course_cm.content_type, COURSE)
        self.assertEqual(course_cm.parent_content_key, None)
        self.assertEqual(course_cm.json_metadata, course_metadata)

        course_run_cm = ContentMetadata.objects.get(content_key=course_run_metadata['key'])
        self.assertEqual(course_run_cm.content_type, COURSE_RUN)
        self.assertEqual(course_run_cm.parent_content_key, course_metadata['key'])
        self.assertEqual(course_run_cm.json_metadata, course_run_metadata)

        program_cm = ContentMetadata.objects.get(content_key=program_metadata['uuid'])
        self.assertEqual(program_cm.content_type, PROGRAM)
        self.assertEqual(program_cm.parent_content_key, None)
        self.assertEqual(program_cm.json_metadata, program_metadata)
