import mock
from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.management.commands.reindex_algolia import (
    ALGOLIA_FIELDS,
    ALGOLIA_INDEX_SETTINGS,
    BATCH_SIZE,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


class ReindexAlgoliaCommandTests(TestCase):
    command_name = 'reindex_algolia'

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.reindex_algolia.AlgoliaSearchClient'
    )
    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.reindex_algolia.index_enterprise_catalog_courses_in_algolia_task'
    )
    def test_reindex_algolia(self, mock_task, mock_search_client):
        """
        Verify that the job spins off the correct number of index_enterprise_catalog_courses_in_algolia_task
        """
        # create enough ContentMetadata records to force more than 1 batch of content keys
        content_metadata = ContentMetadataFactory.create_batch(
            BATCH_SIZE + 1,
            content_type=COURSE,
        )
        content_keys = [metadata.content_key for metadata in content_metadata]

        call_command(self.command_name)

        # verify Algolia index is initialized and configured
        mock_search_client.return_value.init_index.assert_called_once()
        mock_search_client.return_value.set_index_settings.assert_called_once_with(ALGOLIA_INDEX_SETTINGS)

        # verify batching of content keys works as expected
        expected_call_args = []
        mock_task_calls = mock_task.delay.call_args_list
        assert len(mock_task_calls) == 2

        # verify both calls are made with correct kwargs
        __, kwargs = mock_task_calls[0]
        assert kwargs == {
            'algolia_fields': ALGOLIA_FIELDS,
            'content_keys': content_keys[:-1],
        }
        __, kwargs = mock_task_calls[1]
        assert kwargs == {
            'algolia_fields': ALGOLIA_FIELDS,
            'content_keys': [content_keys[-1]],
        }
