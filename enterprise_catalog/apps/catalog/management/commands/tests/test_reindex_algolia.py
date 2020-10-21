from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.catalog.algolia_utils import ALGOLIA_FIELDS
from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


PATH_PREFIX = 'enterprise_catalog.apps.catalog.management.commands.reindex_algolia.'


class ReindexAlgoliaCommandTests(TestCase):
    command_name = 'reindex_algolia'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.number_of_metadata_items = 3
        cls.content_metadata = ContentMetadataFactory.create_batch(cls.number_of_metadata_items, content_type=COURSE)
        cls.content_keys = [metadata.content_key for metadata in cls.content_metadata]

    @mock.patch(PATH_PREFIX + 'get_indexable_course_keys')
    @mock.patch(PATH_PREFIX + 'get_initialized_algolia_client', mock.MagicMock())
    @mock.patch(PATH_PREFIX + 'index_enterprise_catalog_courses_in_algolia_task')
    def test_reindex_algolia(self, mock_task, mock_get_indexable_course_keys):
        """
        Verify that the job spins off the correct number of index_enterprise_catalog_courses_in_algolia_task
        """
        # Mock that all the class content keys are indexable course keys
        mock_get_indexable_course_keys.return_value = self.content_keys

        with mock.patch(PATH_PREFIX + 'TASK_BATCH_SIZE', 1):
            call_command(self.command_name)

            assert mock_task.delay.call_count == self.number_of_metadata_items
            expected_calls = [
                mock.call(content_keys=[content_key], algolia_fields=ALGOLIA_FIELDS)
                for content_key in self.content_keys
            ]
            mock_task.delay.assert_has_calls(expected_calls, any_order=True)
