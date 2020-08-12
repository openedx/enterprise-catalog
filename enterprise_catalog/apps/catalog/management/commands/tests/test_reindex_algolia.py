from uuid import uuid4

import ddt
import mock
from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.management.commands.reindex_algolia import (
    ALGOLIA_FIELDS,
    ALGOLIA_INDEX_SETTINGS,
    BATCH_SIZE,
    should_index,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


@ddt.ddt
class ReindexAlgoliaCommandTests(TestCase):
    command_name = 'reindex_algolia'

    @ddt.data(
        {'expected_result': False, 'has_advertised_course_run': False},
        {'expected_result': False, 'has_owners': False},
        {'expected_result': False, 'has_url_slug': False},
        {'expected_result': False, 'advertised_course_run_hidden': True},
        {'expected_result': True},
    )
    @ddt.unpack
    def test_should_index(
        self,
        expected_result,
        has_advertised_course_run=True,
        has_owners=True,
        has_url_slug=True,
        advertised_course_run_hidden=False,
    ):
        """
        Verify that only a course that has a non-hidden advertised course run, at least one owner, and a marketing slug
        is marked as indexable.
        """
        advertised_course_run_uuid = uuid4()
        course_run_uuid = advertised_course_run_uuid if has_advertised_course_run else uuid4()
        owners = [{'name': 'edX'}] if has_owners else []
        url_slug = 'test-slug' if has_url_slug else ''
        json_metadata = {
            'advertised_course_run_uuid': advertised_course_run_uuid,
            'course_runs': [
                {
                    'hidden': advertised_course_run_hidden,
                    'uuid': course_run_uuid,
                },
            ],
            'owners': owners,
            'url_slug': url_slug,
        }
        course_metadata = ContentMetadataFactory.create(
            content_type=COURSE,
            json_metadata=json_metadata,
        )
        assert should_index(course_metadata) is expected_result

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.reindex_algolia.should_index'
    )
    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.reindex_algolia.AlgoliaSearchClient'
    )
    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.reindex_algolia.index_enterprise_catalog_courses_in_algolia_task'
    )
    def test_reindex_algolia(self, mock_task, mock_search_client, mock_should_index):
        """
        Verify that the job spins off the correct number of index_enterprise_catalog_courses_in_algolia_task
        """
        # Mock that all courses should be indexed
        mock_should_index.return_value = True
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
