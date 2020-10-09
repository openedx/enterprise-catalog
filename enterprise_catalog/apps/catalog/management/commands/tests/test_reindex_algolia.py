from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.catalog.algolia_utils import ALGOLIA_FIELDS
from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


class ReindexAlgoliaCommandTests(TestCase):
    command_name = 'reindex_algolia'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.content_metadata = ContentMetadataFactory.create_batch(3, content_type=COURSE)
        cls.content_keys = [metadata.content_key for metadata in cls.content_metadata]

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.reindex_algolia.get_indexable_course_keys',
    )
    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.reindex_algolia.get_initialized_algolia_client',
        mock.MagicMock(),
    )
    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.reindex_algolia.index_enterprise_catalog_courses_in_algolia_task'
    )
    def test_reindex_algolia(self, mock_task, mock_get_indexable_course_keys):
        """
        Verify that the job spins off the correct number of index_enterprise_catalog_courses_in_algolia_task
        """
        # Mock that all the class content keys are indexable course keys
        mock_get_indexable_course_keys.return_value = self.content_keys

        call_command(self.command_name)

        mock_task.delay.assert_called_once_with(
            content_keys=self.content_keys,
            algolia_fields=ALGOLIA_FIELDS,
        )
