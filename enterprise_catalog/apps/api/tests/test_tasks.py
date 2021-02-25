"""
Tests for the enterprise_catalog API celery tasks
"""
import uuid
from datetime import timedelta
from unittest import mock

import ddt
from celery import states
from django.test import TestCase
from django_celery_results.models import TaskResult

from enterprise_catalog.apps.api import tasks
from enterprise_catalog.apps.catalog.constants import COURSE, COURSE_RUN
from enterprise_catalog.apps.catalog.models import ContentMetadata
from enterprise_catalog.apps.catalog.tests.factories import (
    CatalogQueryFactory,
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
)
from enterprise_catalog.apps.catalog.utils import localized_utcnow


# An object that represents the output of some hard work done by a task.
COMPUTED_PRECIOUS_OBJECT = object()


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
            task_args=str(self.test_args),
            task_kwargs=str(self.test_kwargs),
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
        self.mock_task_result.task_kwargs = str({})
        self.mock_task_result.save()

        with self.assertRaises(tasks.TaskRecentlyRunError):
            self.mock_task_instance(*self.test_args)

    def test_semaphore_raises_recent_run_error_for_same_kwargs(self):
        self.mock_task_result.task_args = str(tuple())
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
    @mock.patch('enterprise_catalog.apps.api.tasks.get_indexable_course_keys')
    @mock.patch('enterprise_catalog.apps.api_client.base_oauth.OAuthAPIClient')
    def test_update_full_metadata(self, mock_oauth_client, mock_get_indexable_course_keys, mock_task_recently_run):
        """
        Assert that full course metadata is merged with original json_metadata for all ContentMetadata records.
        """
        course_key_1 = 'fakeX'
        course_data_1 = {'key': course_key_1, 'full_course_only_field': 'test_1'}
        course_key_2 = 'testX'
        course_data_2 = {'key': course_key_2, 'full_course_only_field': 'test_2'}
        non_course_key = 'course-runX'

        # Mock out the data that should be returned from discovery's /api/v1/courses endpoint
        mock_oauth_client.return_value.get.return_value.json.return_value = {
            'results': [course_data_1, course_data_2],
        }

        metadata_1 = ContentMetadataFactory(content_type=COURSE, content_key=course_key_1)
        metadata_1.catalog_queries.set([self.catalog_query])
        metadata_2 = ContentMetadataFactory(content_type=COURSE, content_key=course_key_2)
        metadata_2.catalog_queries.set([self.catalog_query])
        non_course_metadata = ContentMetadataFactory(content_type=COURSE_RUN, content_key=non_course_key)
        non_course_metadata.catalog_queries.set([self.catalog_query])

        assert metadata_1.json_metadata != course_data_1
        assert metadata_2.json_metadata != course_data_2

        mock_get_indexable_course_keys.return_value = [course_key_1, course_key_2]
        indexable_course_keys = tasks.update_full_content_metadata_task.apply().get()
        # Verify the task returns the course keys that are indexable as those keys are passed to the
        # `index_enterprise_catalog_courses_in_algolia_task` from the `EnterpriseCatalogRefreshDataFromDiscovery` view.
        assert indexable_course_keys == mock_get_indexable_course_keys.return_value

        metadata_1 = ContentMetadata.objects.get(content_key='fakeX')
        metadata_2 = ContentMetadata.objects.get(content_key='testX')

        # add aggregation_key and uuid to course objects since they should now exist
        # after merging the original json_metadata with the course metadata
        course_data_1.update({
            'uuid': metadata_1.json_metadata.get('uuid'),
            'aggregation_key': 'course:fakeX',
            'marketing_url': metadata_1.json_metadata.get('marketing_url'),
            'image_url': metadata_1.json_metadata.get('image_url'),
            'owners': metadata_1.json_metadata.get('owners'),
        })
        course_data_2.update({
            'uuid': metadata_2.json_metadata.get('uuid'),
            'aggregation_key': 'course:testX',
            'marketing_url': metadata_2.json_metadata.get('marketing_url'),
            'image_url': metadata_2.json_metadata.get('image_url'),
            'owners': metadata_2.json_metadata.get('owners'),
        })

        assert metadata_1.json_metadata == course_data_1
        assert metadata_2.json_metadata == course_data_2


class IndexEnterpriseCatalogCoursesInAlgoliaTaskTests(TestCase):
    """
    Tests for `index_enterprise_catalog_courses_in_algolia_task`
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ALGOLIA_FIELDS = ['key', 'objectID', 'enterprise_customer_uuids', 'enterprise_catalog_uuids']

        # Set up a catalog, query, and metadata for a course
        cls.enterprise_catalog_courses = EnterpriseCatalogFactory()
        courses_catalog_query = cls.enterprise_catalog_courses.catalog_query
        cls.course_metadata = ContentMetadataFactory(content_type=COURSE, content_key='fakeX')
        cls.course_metadata.catalog_queries.set([courses_catalog_query])

        # Set up new catalog, query, and metadata for a course run
        cls.enterprise_catalog_course_runs = EnterpriseCatalogFactory()
        course_runs_catalog_query = cls.enterprise_catalog_course_runs.catalog_query
        course_run_metadata = ContentMetadataFactory(content_type=COURSE_RUN, parent_content_key='fakeX')
        course_run_metadata.catalog_queries.set([course_runs_catalog_query])

    def _set_up_factory_data_for_algolia(self):
        expected_catalog_uuids = sorted([
            str(self.enterprise_catalog_courses.uuid),
            str(self.enterprise_catalog_course_runs.uuid)
        ])
        expected_customer_uuids = sorted([
            str(self.enterprise_catalog_courses.enterprise_uuid),
            str(self.enterprise_catalog_course_runs.enterprise_uuid),
        ])

        return {
            'catalog_uuids': expected_catalog_uuids,
            'customer_uuids': expected_customer_uuids,
            'course_metadata': self.course_metadata,
        }

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    def test_index_algolia_with_all_uuids(self, mock_search_client):
        """
        Assert that the correct data is sent to Algolia index, with the expected enterprise
        catalog and enterprise customer associations.
        """
        algolia_data = self._set_up_factory_data_for_algolia()

        tasks.index_enterprise_catalog_courses_in_algolia_task(
            content_keys=['fakeX'],
            algolia_fields=self.ALGOLIA_FIELDS,
        )

        # create expected Algolia data
        expected_algolia_objects = []
        course_uuid = algolia_data['course_metadata'].json_metadata.get('uuid')
        expected_algolia_objects.append({
            'key': algolia_data['course_metadata'].content_key,
            'objectID': f'course-{course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': algolia_data['catalog_uuids'],
        })
        expected_algolia_objects.append({
            'key': algolia_data['course_metadata'].content_key,
            'objectID': f'course-{course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': algolia_data['customer_uuids'],
        })

        # verify partially_update_index is called with the correct Algolia object data
        mock_search_client().partially_update_index.assert_called_once_with(expected_algolia_objects)

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    def test_index_algolia_with_batched_uuids(self, mock_search_client):
        """
        Assert that the correct data is sent to Algolia index, with the expected enterprise
        catalog and enterprise customer associations.
        """
        algolia_data = self._set_up_factory_data_for_algolia()

        tasks.index_enterprise_catalog_courses_in_algolia_task(
            content_keys=['fakeX'],
            algolia_fields=self.ALGOLIA_FIELDS,
            uuid_batch_size=1,
        )

        # create expected Algolia data
        expected_algolia_objects = []
        course_uuid = algolia_data['course_metadata'].json_metadata.get('uuid')
        expected_algolia_objects.append({
            'key': algolia_data['course_metadata'].content_key,
            'objectID': f'course-{course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': [algolia_data['catalog_uuids'][0]],
        })
        expected_algolia_objects.append({
            'key': algolia_data['course_metadata'].content_key,
            'objectID': f'course-{course_uuid}-catalog-uuids-1',
            'enterprise_catalog_uuids': [algolia_data['catalog_uuids'][1]],
        })
        expected_algolia_objects.append({
            'key': algolia_data['course_metadata'].content_key,
            'objectID': f'course-{course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': [algolia_data['customer_uuids'][0]],
        })
        expected_algolia_objects.append({
            'key': algolia_data['course_metadata'].content_key,
            'objectID': f'course-{course_uuid}-customer-uuids-1',
            'enterprise_customer_uuids': [algolia_data['customer_uuids'][1]],
        })

        # verify partially_update_index is called with the correct Algolia object data
        mock_search_client().partially_update_index.assert_called_once_with(expected_algolia_objects)
