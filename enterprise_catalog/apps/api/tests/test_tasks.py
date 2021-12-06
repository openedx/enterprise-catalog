"""
Tests for the enterprise_catalog API celery tasks
"""
import json
import uuid
from datetime import timedelta
from unittest import mock

import ddt
from celery import states
from django.test import TestCase
from django_celery_results.models import TaskResult

from enterprise_catalog.apps.api import tasks
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    PROGRAM,
)
from enterprise_catalog.apps.catalog.models import CatalogQuery, ContentMetadata
from enterprise_catalog.apps.catalog.tests.factories import (
    CatalogQueryFactory,
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
)
from enterprise_catalog.apps.catalog.utils import localized_utcnow


# An object that represents the output of some hard work done by a task.
COMPUTED_PRECIOUS_OBJECT = object()
SORTED_QUERY_UUID_LIST = sorted([uuid.uuid4(), uuid.uuid4()])


@tasks.expiring_task_semaphore()
def mock_task(self, *args, **kwargs):  # pylint: disable=unused-argument
    """
    A mock task that is constrained by our expiring semaphore mechanism.
    """
    return COMPUTED_PRECIOUS_OBJECT


# An actual celery task would have a name attribute, and we use
# it in a few places, so we patch it in here.
mock_task.name = 'mock_task'


@ddt.ddt
class TestTaskResultFunctions(TestCase):
    """
    Tests for functions in tasks.py that rely upon `django-celery_results.models.TaskResult`.
    """
    def setUp(self):
        """
        Delete all TaskResult objects, make a new single result object.
        """
        super().setUp()
        TaskResult.objects.all().delete()

        self.test_args = (123, 77)
        self.test_kwargs = {'foo': 'bar'}

        self.mock_task_id = uuid.uuid4()
        self.other_task_id = uuid.uuid4()

        self.mock_task_result = TaskResult.objects.create(
            task_name=mock_task.name,
            task_args=json.dumps(self.test_args),
            task_kwargs=json.dumps(self.test_kwargs),
            status=states.SUCCESS,
            # Default to a state where the only recorded task result is for some "other" task
            task_id=self.other_task_id,
        )

    def mock_task_instance(self, *args, **kwargs):
        """
        Helper method that creates a "bound task object", which is a stand-in
        for what `self` would be in the body of a celery task that has `bind=True` specified.
        Invokes our `mock_task` with that bound object and the given args and kwargs.
        """
        bound_task_object = mock.MagicMock()
        bound_task_object.name = mock_task.name
        bound_task_object.request.id = self.mock_task_id
        bound_task_object.request.args = args
        bound_task_object.request.kwargs = kwargs
        return mock_task(bound_task_object, *args, **kwargs)

    def test_semaphore_raises_recent_run_error_for_same_args(self):
        self.mock_task_result.task_kwargs = '{}'
        self.mock_task_result.save()

        with self.assertRaises(tasks.TaskRecentlyRunError):
            self.mock_task_instance(*self.test_args)

    def test_semaphore_raises_recent_run_error_for_same_kwargs(self):
        self.mock_task_result.task_args = '[]'
        self.mock_task_result.save()

        with self.assertRaises(tasks.TaskRecentlyRunError):
            self.mock_task_instance(**self.test_kwargs)

    def test_task_with_result_older_than_an_hour_ignored_by_semaphore(self):
        self.mock_task_result.date_created = localized_utcnow() - timedelta(hours=4)
        self.mock_task_result.save()

        result = self.mock_task_instance(*self.test_args, **self.test_kwargs)
        assert COMPUTED_PRECIOUS_OBJECT == result

    @ddt.data(states.FAILURE, states.REVOKED)
    def test_failed_or_revoked_tasks_are_ignored_by_semaphore(self, task_state):
        self.mock_task_result.status = task_state
        self.mock_task_result.date_created = localized_utcnow() - timedelta(minutes=1)
        self.mock_task_result.save()

        result = self.mock_task_instance(*self.test_args)
        assert result == COMPUTED_PRECIOUS_OBJECT

    def test_given_task_id_is_ignored_by_semaphore(self):
        # Make our only TaskResult for a task with the same id
        # as the mock task - set status and date such that the
        # result would count as a recent equivalent task if it did _not_
        # have the same task_id as the mock task that is "running".
        self.mock_task_result.status = states.PENDING
        self.mock_task_result.date_created = localized_utcnow() - timedelta(minutes=1)
        self.mock_task_result.task_id = self.mock_task_id
        self.mock_task_result.save()

        result = self.mock_task_instance(*self.test_args, **self.test_kwargs)
        assert COMPUTED_PRECIOUS_OBJECT == result

    @ddt.data(*states.UNREADY_STATES)
    def test_unready_tasks_exist_for_unready_states(self, task_state):
        self.mock_task_result.status = task_state
        self.mock_task_result.save()

        self.assertTrue(
            tasks.unready_tasks(
                mock_task, timedelta(hours=2)
            ).exists()
        )

    @ddt.data(*states.READY_STATES)
    def test_unready_tasks_dont_exist_for_ready_states(self, task_state):
        self.mock_task_result.status = task_state
        self.mock_task_result.save()

        self.assertFalse(
            tasks.unready_tasks(
                mock_task, timedelta(hours=2)
            ).exists()
        )

    def test_unready_tasks_dont_exist_for_more_recent_delta(self):
        self.mock_task_result.status = states.PENDING
        self.mock_task_result.date_created = localized_utcnow() - timedelta(hours=1)
        self.mock_task_result.save()

        self.assertFalse(
            tasks.unready_tasks(
                mock_task, timedelta(minutes=30)
            ).exists()
        )

    def test_unready_tasks_dont_exist_for_different_task_name(self):
        other_mock_task = mock.MagicMock()
        other_mock_task.name = 'other_task_name'

        self.assertFalse(
            tasks.unready_tasks(
                other_mock_task, timedelta(hours=24)
            ).exists()
        )


class UpdateCatalogMetadataTaskTests(TestCase):
    """
    Tests for the `update_catalog_metadata_task`.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.catalog_query = CatalogQueryFactory()

    @mock.patch('enterprise_catalog.apps.api.tasks.update_contentmetadata_from_discovery')
    def test_update_catalog_metadata(self, mock_update_data_from_discovery):
        """
        Assert update_catalog_metadata_task is called with correct catalog_query_id
        """
        tasks.update_catalog_metadata_task.apply(args=(self.catalog_query.id,))
        mock_update_data_from_discovery.assert_called_with(self.catalog_query)

    @mock.patch('enterprise_catalog.apps.api.tasks.update_contentmetadata_from_discovery')
    def test_update_catalog_metadata_no_catalog_query(self, mock_update_data_from_discovery):
        """
        Assert that discovery is not called if a bad catalog query id is passed
        """
        bad_id = 412
        tasks.update_catalog_metadata_task.apply(args=(bad_id,))
        mock_update_data_from_discovery.assert_not_called()


class FetchMissingCourseMetadataTaskTests(TestCase):
    """
    Tests for the `fetch_missing_course_metadata_task`.
    """
    @mock.patch('enterprise_catalog.apps.api.tasks.update_contentmetadata_from_discovery')
    def test_fetch_missing_course_metadata_task(self, mock_update_data_from_discovery):
        """
        Validate the fetch_missing_course_metadata_task gathers correct data of missing courses and calls
        update_contentmetadata_from_discovery with correct arguments.
        """
        test_course = 'course:edX+testX'
        course_content_metadata = ContentMetadataFactory.create(content_type=COURSE)
        ContentMetadataFactory.create(content_type=PROGRAM, json_metadata={
            'courses': [
                course_content_metadata.json_metadata,
                {
                    'key': test_course,
                },
            ]
        })

        tasks.fetch_missing_course_metadata_task.apply()

        assert CatalogQuery.objects.filter().count() == 1
        catalog_query = CatalogQuery.objects.first()
        assert catalog_query.content_filter['status'] == 'published'
        assert catalog_query.content_filter['content_type'] == 'course'
        assert catalog_query.content_filter['key'] == [test_course]

        mock_update_data_from_discovery.assert_called_with(catalog_query)


class UpdateFullContentMetadataTaskTests(TestCase):
    """
    Tests for the `update_full_content_metadata_task`.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.enterprise_catalog = EnterpriseCatalogFactory()
        cls.catalog_query = cls.enterprise_catalog.catalog_query

    # pylint: disable=unused-argument
    @mock.patch('enterprise_catalog.apps.api.tasks.task_recently_run', return_value=False)
    @mock.patch('enterprise_catalog.apps.api.tasks.partition_course_keys_for_indexing')
    @mock.patch('enterprise_catalog.apps.api_client.base_oauth.OAuthAPIClient')
    def test_update_full_metadata(self, mock_oauth_client, mock_partition_course_keys, mock_task_recently_run):
        """
        Assert that full course metadata is merged with original json_metadata for all ContentMetadata records.
        """
        program_key = '02f5edeb-6604-4131-bf45-acd8df91e1f9'
        program_data = {'uuid': program_key, 'full_program_only_field': 'test_1'}
        course_key_1 = 'fakeX'
        course_data_1 = {'key': course_key_1, 'full_course_only_field': 'test_1', 'programs': []}
        course_key_2 = 'testX'
        course_data_2 = {'key': course_key_2, 'full_course_only_field': 'test_2', 'programs': [program_data]}

        non_course_key = 'course-runX'

        # Mock out the data that should be returned from discovery's /api/v1/courses and /api/v1/programs endpoints
        mock_oauth_client.return_value.get.return_value.json.side_effect = [
            {
                'results': [course_data_1, course_data_2],  # first call will be /api/v1/courses
            },
            {
                'results': [program_data],                  # second call will be to /api/v1/programs
            }
        ]
        mock_partition_course_keys.return_value = ([], [],)

        metadata_1 = ContentMetadataFactory(content_type=COURSE, content_key=course_key_1)
        metadata_1.catalog_query_mapping.set([self.catalog_query])
        metadata_2 = ContentMetadataFactory(content_type=COURSE, content_key=course_key_2)
        metadata_2.catalog_query_mapping.set([self.catalog_query])
        non_course_metadata = ContentMetadataFactory(content_type=COURSE_RUN, content_key=non_course_key)
        non_course_metadata.catalog_query_mapping.set([self.catalog_query])

        assert metadata_1.json_metadata != course_data_1
        assert metadata_2.json_metadata != course_data_2

        tasks.update_full_content_metadata_task.apply().get()

        actual_course_keys_args = mock_partition_course_keys.call_args_list[0][0][0]
        self.assertEqual(set(actual_course_keys_args), {metadata_1, metadata_2})

        metadata_1 = ContentMetadata.objects.get(content_key='fakeX')
        metadata_2 = ContentMetadata.objects.get(content_key='testX')

        # add aggregation_key and uuid to course objects since they should now exist
        # after merging the original json_metadata with the course metadata
        course_data_1.update(metadata_1.json_metadata)
        course_data_2.update(metadata_2.json_metadata)
        course_data_1.update({'aggregation_key': 'course:fakeX'})
        course_data_2.update({'aggregation_key': 'course:testX'})

        assert metadata_1.json_metadata == course_data_1
        assert metadata_2.json_metadata == course_data_2

        # make sure course associated program metadata has been created and linked correctly
        assert ContentMetadata.objects.filter(content_key=program_key).exists()
        assert metadata_2.associated_content_metadata.filter(content_key=program_key).exists()
        assert not metadata_1.associated_content_metadata.filter(content_key=program_key).exists()

    # pylint: disable=unused-argument
    @mock.patch('enterprise_catalog.apps.api.tasks.task_recently_run', return_value=False)
    @mock.patch('enterprise_catalog.apps.api.tasks.partition_program_keys_for_indexing')
    @mock.patch('enterprise_catalog.apps.api_client.base_oauth.OAuthAPIClient')
    def test_update_full_metadata_program(self, mock_oauth_client, mock_partition_program_keys, mock_task_recently_run):
        """
        Assert that full program metadata is merged with original json_metadata for all ContentMetadata records.
        """
        program_key_1 = '02f5edeb-6604-4131-bf45-acd8df91e1f9'
        program_data_1 = {'uuid': program_key_1, 'full_program_only_field': 'test_1'}
        program_key_2 = 'be810df3-a059-42a7-b11f-d9bfb2877b15'
        program_data_2 = {'uuid': program_key_2, 'full_program_only_field': 'test_2'}

        # Mock out the data that should be returned from discovery's /api/v1/programs endpoint
        mock_oauth_client.return_value.get.return_value.json.return_value = {
            'results': [program_data_1, program_data_2],
        }
        mock_partition_program_keys.return_value = ([], [],)

        metadata_1 = ContentMetadataFactory(content_type=PROGRAM, content_key=program_key_1)
        metadata_1.catalog_query_mapping.set([self.catalog_query])
        metadata_2 = ContentMetadataFactory(content_type=PROGRAM, content_key=program_key_2)
        metadata_2.catalog_query_mapping.set([self.catalog_query])

        assert metadata_1.json_metadata != program_data_1
        assert metadata_2.json_metadata != program_data_2

        tasks.update_full_content_metadata_task.apply().get()

        actual_program_keys_args = mock_partition_program_keys.call_args_list[0][0][0]
        self.assertEqual(set(actual_program_keys_args), {metadata_1, metadata_2})

        metadata_1 = ContentMetadata.objects.get(content_key='02f5edeb-6604-4131-bf45-acd8df91e1f9')
        metadata_2 = ContentMetadata.objects.get(content_key='be810df3-a059-42a7-b11f-d9bfb2877b15')

        # add aggregation_key and uuid to program objects since they should now exist
        # after merging the original json_metadata with the course metadata
        program_data_1.update(metadata_1.json_metadata)
        program_data_2.update(metadata_2.json_metadata)
        program_data_1.update({'aggregation_key': 'program:02f5edeb-6604-4131-bf45-acd8df91e1f9'})
        program_data_2.update({'aggregation_key': 'program:be810df3-a059-42a7-b11f-d9bfb2877b15'})

        assert metadata_1.json_metadata == program_data_1
        assert metadata_2.json_metadata == program_data_2


class IndexEnterpriseCatalogCoursesInAlgoliaTaskTests(TestCase):
    """
    Tests for `index_enterprise_catalog_in_algolia_task`
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ALGOLIA_FIELDS = [
            'key',
            'objectID',
            'enterprise_customer_uuids',
            'enterprise_catalog_uuids',
            'enterprise_catalog_query_uuids',
            'enterprise_catalog_query_titles',
        ]

        # Set up a catalog, query, and metadata for a course and course associated program
        cls.enterprise_catalog_query = CatalogQueryFactory(uuid=SORTED_QUERY_UUID_LIST[0])
        cls.enterprise_catalog_courses = EnterpriseCatalogFactory(catalog_query=cls.enterprise_catalog_query)
        cls.course_metadata_published = ContentMetadataFactory(content_type=COURSE, content_key='fakeX')

        cls.course_metadata_published.catalog_query_mapping.set([cls.enterprise_catalog_query])
        cls.course_metadata_unpublished = ContentMetadataFactory(content_type=COURSE, content_key='testX')
        cls.course_metadata_unpublished.json_metadata.get('course_runs')[0].update({
            'status': 'unpublished',
        })
        cls.course_metadata_unpublished.catalog_query_mapping.set([cls.enterprise_catalog_query])
        cls.course_metadata_unpublished.save()
        cls.course_associated_program_metadata = ContentMetadataFactory(content_type=PROGRAM, content_key='program-1')
        cls.course_metadata_published.associated_content_metadata.set([cls.course_associated_program_metadata])

        # Set up new catalog, query, and metadata for a course run
        # Testing indexing catalog queries when titles aren't present
        cls.course_run_catalog_query = CatalogQueryFactory(uuid=SORTED_QUERY_UUID_LIST[1], title=None)
        cls.enterprise_catalog_course_runs = EnterpriseCatalogFactory(catalog_query=cls.course_run_catalog_query)

        course_runs_catalog_query = cls.enterprise_catalog_course_runs.catalog_query
        course_run_metadata_published = ContentMetadataFactory(content_type=COURSE_RUN, parent_content_key='fakeX')
        course_run_metadata_published.catalog_query_mapping.set([course_runs_catalog_query])
        course_run_metadata_unpublished = ContentMetadataFactory(content_type=COURSE_RUN, parent_content_key='testX')
        course_run_metadata_unpublished.json_metadata.update({
            'status': 'unpublished',
        })
        course_run_metadata_unpublished.catalog_query_mapping.set([course_runs_catalog_query])
        course_run_metadata_unpublished.save()

    def _set_up_factory_data_for_algolia(self):
        expected_catalog_uuids = sorted([
            str(self.enterprise_catalog_courses.uuid),
            str(self.enterprise_catalog_course_runs.uuid)
        ])
        expected_customer_uuids = sorted([
            str(self.enterprise_catalog_courses.enterprise_uuid),
            str(self.enterprise_catalog_course_runs.enterprise_uuid),
        ])
        expected_queries = sorted([(
            str(self.enterprise_catalog_courses.catalog_query.uuid),
            self.enterprise_catalog_courses.catalog_query.title,
        ), (
            str(self.enterprise_catalog_course_runs.catalog_query.uuid),
            None,
        )])

        query_uuids, query_titles = list(map(list, zip(*expected_queries)))
        return {
            'catalog_uuids': expected_catalog_uuids,
            'customer_uuids': expected_customer_uuids,
            'query_uuids': query_uuids,
            'query_titles': query_titles,
            'course_metadata_published': self.course_metadata_published,
            'course_metadata_unpublished': self.course_metadata_unpublished,
            'course_associated_program_metadata': self.course_associated_program_metadata,
        }

    @mock.patch('enterprise_catalog.apps.api.tasks._was_recently_indexed', side_effect=[False, True])
    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    def test_index_algolia_with_all_uuids(self, mock_search_client, mock_was_recently_indexed):
        """
        Assert that the correct data is sent to Algolia index, with the expected enterprise
        catalog and enterprise customer associations.
        """
        algolia_data = self._set_up_factory_data_for_algolia()

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS):
            tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter
            # call it a second time, make assertions that only one thing happened below
            tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        # create expected data to be added/updated in the Algolia index.
        expected_algolia_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': algolia_data['catalog_uuids'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': algolia_data['customer_uuids'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted(algolia_data['query_uuids']),
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
        })

        # verify replace_all_objects is called with the correct Algolia object data
        # on the first invocation and with an empty list on the second invocation.
        mock_search_client().replace_all_objects.assert_has_calls([
            mock.call(expected_algolia_objects_to_index),
            mock.call([]),
        ])

        # Verify that we checked the cache twice, though
        mock_was_recently_indexed.assert_has_calls([
            mock.call(self.course_metadata_published.content_key),
            mock.call(self.course_metadata_published.content_key),
        ])

    @mock.patch('enterprise_catalog.apps.api.tasks._was_recently_indexed', return_value=False)
    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    def test_index_algolia_with_batched_uuids(self, mock_search_client, mock_was_recently_indexed):
        """
        Assert that the correct data is sent to Algolia index, with the expected enterprise
        catalog, enterprise customer, and catalog query associations.
        """
        algolia_data = self._set_up_factory_data_for_algolia()

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_UUID_BATCH_SIZE', 1), \
             mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS):
            tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        # create expected data to be added/updated in the Algolia index.
        expected_algolia_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': [algolia_data['catalog_uuids'][0]],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-1',
            'enterprise_catalog_uuids': [algolia_data['catalog_uuids'][1]],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': [algolia_data['customer_uuids'][0]],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-1',
            'enterprise_customer_uuids': [algolia_data['customer_uuids'][1]],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': [algolia_data['query_uuids'][0]],
            'enterprise_catalog_query_titles': [algolia_data['query_titles'][0]],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-1',
            'enterprise_catalog_query_uuids': [algolia_data['query_uuids'][1]],
            'enterprise_catalog_query_titles': [],
        })

        # verify replace_all_objects is called with the correct Algolia object data
        mock_search_client().replace_all_objects.assert_called_once_with(expected_algolia_objects_to_index)

        mock_was_recently_indexed.assert_called_once_with(self.course_metadata_published.content_key)

    @mock.patch('enterprise_catalog.apps.api.tasks._was_recently_indexed', return_value=False)
    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    def test_index_algolia_with_important_catalog_titles(self, mock_search_client, mock_was_recently_indexed):
        """
        Assert that every Algolia batch contains all the explore UI catalog titles
        """
        algolia_data = self._set_up_factory_data_for_algolia()
        # override the explore UI titles with test data to show every batch contains them
        explore_titles = [algolia_data['query_titles'][0]]

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_UUID_BATCH_SIZE', 1), \
             mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS), \
             mock.patch('enterprise_catalog.apps.api.tasks.EXPLORE_CATALOG_TITLES', explore_titles):
            tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        # create expected data to be added/updated in the Algolia index.
        expected_algolia_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': [algolia_data['catalog_uuids'][0]],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-1',
            'enterprise_catalog_uuids': [algolia_data['catalog_uuids'][1]],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': [algolia_data['customer_uuids'][0]],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-1',
            'enterprise_customer_uuids': [algolia_data['customer_uuids'][1]],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': [algolia_data['query_uuids'][0]],
            'enterprise_catalog_query_titles': [algolia_data['query_titles'][0]],
        })

        # the title is also in the second batch
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-1',
            'enterprise_catalog_query_uuids': [algolia_data['query_uuids'][1]],
            'enterprise_catalog_query_titles': [algolia_data['query_titles'][0]],
        })

        # verify replace_all_objects is called with the correct Algolia object data
        mock_search_client().replace_all_objects.assert_called_once_with(expected_algolia_objects_to_index)

        mock_was_recently_indexed.assert_called_once_with(self.course_metadata_published.content_key)
