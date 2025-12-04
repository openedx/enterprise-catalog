"""
Tests for the enterprise_catalog API celery tasks
"""
import json
import uuid
from datetime import datetime, timedelta
from operator import itemgetter
from unittest import mock

import ddt
from algoliasearch.exceptions import AlgoliaException
from celery import states
from django.test import TestCase, override_settings
from django_celery_results.models import TaskResult

from enterprise_catalog.apps.academy.tests.factories import AcademyFactory
from enterprise_catalog.apps.api import tasks
from enterprise_catalog.apps.api.constants import CourseMode
from enterprise_catalog.apps.api_client.discovery import CatalogQueryMetadata
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    COURSE_RUN_RESTRICTION_TYPE_KEY,
    EXEC_ED_2U_COURSE_TYPE,
    FORCE_INCLUSION_METADATA_TAG_KEY,
    LEARNER_PATHWAY,
    PROGRAM,
    QUERY_FOR_RESTRICTED_RUNS,
)
from enterprise_catalog.apps.catalog.models import CatalogQuery, ContentMetadata
from enterprise_catalog.apps.catalog.serializers import (
    DEFAULT_NORMALIZED_PRICE,
    NormalizedContentMetadataSerializer,
    _find_best_mode_seat,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    CatalogQueryFactory,
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
    RestrictedCourseMetadataFactory,
    RestrictedRunAllowedForRestrictedCourseFactory,
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


def _hydrate_normalized_metadata(metadata_record):
    """
    Populate normalized_metadata fields for ContentMetadata
    """
    normalized_metadata_input = {
        'course_metadata': metadata_record.json_metadata,
    }
    metadata_record.json_metadata['normalized_metadata'] =\
        NormalizedContentMetadataSerializer(normalized_metadata_input).data
    metadata_record.json_metadata['normalized_metadata_by_run'] = {}
    for run in metadata_record.json_metadata.get('course_runs', []):
        metadata_record.json_metadata['normalized_metadata_by_run'].update({
            run['key']: NormalizedContentMetadataSerializer({
                'course_run_metadata': run,
                'course_metadata': metadata_record.json_metadata,
            }).data
        })


def _hydrate_course_normalized_metadata():
    """
    Populate normalized_metadata fields for all course ContentMetadata
    Needed for tests that generate test ContentMetadata, which does not have
    normalized_metadata populated by default.
    """
    all_course_metadata = ContentMetadata.objects.filter(content_type=COURSE)
    for course_metadata in all_course_metadata:
        _hydrate_normalized_metadata(course_metadata)
        course_metadata.save()


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
            task_args=json.dumps(repr(self.test_args)),
            task_kwargs=json.dumps(repr(self.test_kwargs)),
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
        self.mock_task_result.task_kwargs = json.dumps(repr({}))
        self.mock_task_result.save()

        with self.assertRaises(tasks.TaskRecentlyRunError):
            self.mock_task_instance(*self.test_args)

    def test_semaphore_raises_recent_run_error_for_same_kwargs(self):
        self.mock_task_result.task_args = json.dumps(repr(()))
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
        tasks.update_catalog_metadata_task.apply(args=(self.catalog_query.id, False, False))
        mock_update_data_from_discovery.assert_called_with(self.catalog_query, False)

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
        ContentMetadataFactory.create(content_type=PROGRAM, _json_metadata={
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

        mock_update_data_from_discovery.assert_called_with(catalog_query, False)


@ddt.ddt
class FetchMissingPathwayMetadataTaskTests(TestCase):
    """
    Tests for the `fetch_missing_pathway_metadata_task`.
    """
    @ddt.data(True, False)
    @mock.patch.object(CatalogQueryMetadata, '_get_catalog_query_metadata')
    def test_fetch_missing_pathway_metadata_task(self, visible_via_association, mock_get_catalog_query_metadata):
        """
        Validate the fetch_missing_pathway_metadata_task creates correct Data and its associations.

        1. Validate it creates all the Learner Pathways
        2. Validate it creates missing course and programs associated with Pathways
        3. Validates correct association has been build between pathways ContentMetadata and its associated Course and
        Program ContentMetadata
        """
        test_pathway = 'e246705d-9044-4bc9-8c8d-ebb0c3d0a9ad'
        test_course = 'edX+DemoX'
        test_program = 'dcc9d1cf-a068-48c4-841d-934a0fcd2bfb'

        assert ContentMetadata.objects.count() == 0

        all_pathways_discovery_result = [
            {
                "aggregation_key": f"learnerpathway:{test_pathway}",
                "content_type": "learnerpathway",
                "uuid": test_pathway,
                "name": "Full stack developer",
                "visible_via_association": visible_via_association,
                "status": "active",
                "steps": [
                    {
                        "uuid": "63d708a7-8512-427e-8ae1-6ee8fa685360",
                        "min_requirement": 1,
                        "courses": [],
                        "programs": [
                            {
                                "uuid": test_program,
                                "title": "edX Demonstration Program",
                                "content_type": "program"
                            }
                        ]
                    },
                    {
                        "uuid": "4a169c83-46f6-4a5a-8e58-5ccb76518f3d",
                        "min_requirement": 1,
                        "courses": [
                            {
                                "key": test_course,
                                "title": "Demonstration Course",
                                "content_type": "course"
                            }
                        ],
                        "programs": []
                    }
                ]
            }
        ]
        missing_programs_discovery_result = [
            {
                "aggregation_key": f"program:{test_program}",
                "uuid": test_program,
                "title": "edX Demonstration Program",
                "content_type": "program"
            }
        ]
        missing_courses_discovery_result = [
            {
                "aggregation_key": f"course:{test_course}",
                "key": test_course,
                "title": "Demonstration Course",
                "content_type": "course"
            }
        ]
        mock_get_catalog_query_metadata.side_effect = [
            all_pathways_discovery_result,
            missing_programs_discovery_result,
            missing_courses_discovery_result,
        ]

        tasks.fetch_missing_pathway_metadata_task.apply()

        assert ContentMetadata.objects.count() == 3
        learner_pathway = ContentMetadata.objects.get(content_key=test_pathway)
        program = ContentMetadata.objects.get(content_key=test_program)
        course = ContentMetadata.objects.get(content_key=test_course)
        associated_content_metadata = learner_pathway.associated_content_metadata.all()
        if visible_via_association:
            assert list(associated_content_metadata) == [program, course]
        else:
            assert not associated_content_metadata

        queries = CatalogQuery.objects.all()
        assert queries.count() == 3
        pathways_query = queries[0]
        assert pathways_query.content_filter['content_type'] == LEARNER_PATHWAY

        program_catalog_query = queries[1]
        assert program_catalog_query.content_filter['status'] == 'published'
        assert program_catalog_query.content_filter['content_type'] == 'program'
        assert program_catalog_query.content_filter['key'] == [test_program]

        course_catalog_query = queries[2]
        assert course_catalog_query.content_filter['status'] == 'published'
        assert course_catalog_query.content_filter['content_type'] == 'course'
        assert course_catalog_query.content_filter['key'] == [test_course]


@ddt.ddt
class UpdateFullContentMetadataTaskTests(TestCase):
    """
    Tests for the `update_full_content_metadata_task`.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.enterprise_catalog = EnterpriseCatalogFactory()
        cls.catalog_query = cls.enterprise_catalog.catalog_query

    @ddt.data(
        # Test that it doesn't crash on empty input.
        {
            'seats': [],
            'expected_seat': None,
        },
        # Test that the best seat type is selected (verified > professional).
        {
            'seats': [
                {'type': CourseMode.PROFESSIONAL, 'sku': 'SKU-1'},
                {'type': CourseMode.VERIFIED, 'sku': 'SKU-2'},
            ],
            'expected_seat': {'type': CourseMode.VERIFIED, 'sku': 'SKU-2'},
        },
        # Test that even if one non-"best" seat type is present, the best one is still selected.
        {
            'seats': [
                {'type': CourseMode.PAID_EXECUTIVE_EDUCATION, 'sku': 'SKU-1'},
                {'type': CourseMode.PROFESSIONAL, 'sku': 'SKU-2'},
                {'type': CourseMode.VERIFIED, 'sku': 'SKU-3'},
            ],
            'expected_seat': {'type': CourseMode.VERIFIED, 'sku': 'SKU-3'},
        },
        # Test that even if no "best" seat types are present, one is still selected.
        {
            'seats': [
                {'type': CourseMode.PAID_EXECUTIVE_EDUCATION, 'sku': 'SKU-1'},
            ],
            'expected_seat': {'type': CourseMode.PAID_EXECUTIVE_EDUCATION, 'sku': 'SKU-1'},
        },
    )
    @ddt.unpack
    def test_find_best_mode_seat(self, seats, expected_seat):
        """
        Test the behavior of _find_best_mode_seat().
        """
        assert _find_best_mode_seat(seats) == expected_seat

    # pylint: disable=unused-argument, too-many-statements
    @mock.patch('enterprise_catalog.apps.api.tasks.task_recently_run', return_value=False)
    @mock.patch('enterprise_catalog.apps.api.tasks.partition_course_keys_for_indexing')
    @mock.patch('enterprise_catalog.apps.api_client.base_oauth.OAuthAPIClient')
    def test_update_full_metadata(self, mock_oauth_client, mock_partition_course_keys, mock_task_recently_run):
        """
        Assert that full course metadata is merged with original json_metadata for all ContentMetadata records.
        """
        program_key = '02f5edeb-6604-4131-bf45-acd8df91e1f9'
        program_data = {'uuid': program_key, 'full_program_only_field': 'test_1'}
        course_key_1 = 'edX+fakeX'
        course_data_1 = {'key': course_key_1, 'full_course_only_field': 'test_1', 'programs': []}
        course_key_2 = 'edX+testX'
        course_run_2_uuid = str(uuid.uuid4())
        course_data_2 = {
            'key': course_key_2,
            'full_course_only_field': 'test_2',
            'programs': [program_data],
            'advertised_course_run_uuid': course_run_2_uuid,
            'course_runs': [{
                'uuid': course_run_2_uuid,
                'key': f'course-v1:{course_key_2}+1',
                'start': '2023-03-01T00:00:00Z',
                'end': '2023-03-01T00:00:00Z',
                'first_enrollable_paid_seat_price': None,  # should cause fallback to DEFAULT_NORMALIZED_PRICE
                'seats': [
                    {
                        'type': CourseMode.VERIFIED,
                        'upgrade_deadline': '2023-03-15T00:00:00Z',
                    },
                ],
                'enrollment_start': '2023-02-01T00:00:00Z',
            }],
        }

        course_key_3 = 'edX+fooX'
        course_run_3_uuid = str(uuid.uuid4())
        course_data_3 = {
            'key': course_key_3,
            'programs': [],
            'course_runs': [{
                'key': f'course-v1:{course_key_3}+1',
                'uuid': course_run_3_uuid,
                # The task should copy these dates into net-new top level fields.
                'start': '2023-03-01T00:00:00Z',
                'end': '2023-03-01T00:00:00Z',
                'first_enrollable_paid_seat_price': 90,
                'seats': [
                    {
                        'type': CourseMode.VERIFIED,
                        'upgrade_deadline': '2023-02-01T00:00:00Z',
                    },
                    {
                        "type": str(CourseMode.PROFESSIONAL),
                        "upgrade_deadline": '2022-02-01T00:00:00Z',
                    },
                ],
                'enrollment_start': '2023-02-01T00:00:00Z',
            }],
            'advertised_course_run_uuid': course_run_3_uuid,
        }
        course_key_4 = 'edX+superDuperFakeX'
        course_data_4 = {'key': course_key_4, 'full_course_only_field': 'test_4', 'programs': [], 'course_runs': []}

        non_course_key = 'course-runX'

        mock_oauth_client.return_value.get.return_value.status_code = 200

        # Mock out the data that should be returned from discovery's /api/v1/courses and /api/v1/programs endpoints
        mock_oauth_client.return_value.get.return_value.json.side_effect = [
            # first call will be /api/v1/courses
            {'results': [course_data_1, course_data_2, course_data_3, course_data_4]},
            # second call will be to /api/v1/programs
            {'results': [program_data]},
            {'results': []},
        ]
        mock_partition_course_keys.return_value = ([], [],)

        metadata_1 = ContentMetadataFactory(content_type=COURSE, content_key=course_key_1)
        metadata_1.catalog_queries.set([self.catalog_query])
        metadata_2 = ContentMetadataFactory(content_type=COURSE, content_key=course_key_2)
        metadata_2.catalog_queries.set([self.catalog_query])
        metadata_3 = ContentMetadataFactory(content_type=COURSE, content_key=course_key_3)
        metadata_3.catalog_queries.set([self.catalog_query])
        # Create a metadata record without an advertised course run to test
        # the normalized metadata serializer.
        metadata_4 = ContentMetadataFactory(content_type=COURSE, content_key=course_key_4)
        metadata_4.catalog_queries.set([self.catalog_query])
        metadata_4._json_metadata['advertised_course_run_uuid'] = None  # pylint: disable=protected-access
        metadata_4.save()
        non_course_metadata = ContentMetadataFactory(content_type=COURSE_RUN, content_key=non_course_key)
        non_course_metadata.catalog_queries.set([self.catalog_query])

        assert metadata_1.json_metadata != course_data_1
        assert metadata_2.json_metadata != course_data_2
        assert metadata_3.json_metadata != course_data_3
        assert metadata_4.json_metadata != course_data_4

        tasks.update_full_content_metadata_task.apply().get()

        actual_course_keys_args = mock_partition_course_keys.call_args_list[0][0][0]
        self.assertEqual(set(actual_course_keys_args), {metadata_1, metadata_2, metadata_3, metadata_4})

        metadata_1 = ContentMetadata.objects.get(content_key=course_key_1)
        metadata_2 = ContentMetadata.objects.get(content_key=course_key_2)
        metadata_3 = ContentMetadata.objects.get(content_key=course_key_3)
        metadata_4 = ContentMetadata.objects.get(content_key=course_key_4)

        assert metadata_1.json_metadata['aggregation_key'] == f'course:{course_key_1}'
        assert metadata_1.json_metadata['full_course_only_field'] == 'test_1'
        assert metadata_1.json_metadata['programs'] == []

        assert metadata_2.json_metadata['aggregation_key'] == f'course:{course_key_2}'
        assert metadata_2.json_metadata['full_course_only_field'] == 'test_2'
        assert metadata_2.json_metadata['normalized_metadata']['content_price'] == DEFAULT_NORMALIZED_PRICE
        assert metadata_2.json_metadata['normalized_metadata']['start_date'] == '2023-03-01T00:00:00Z'
        assert metadata_2.json_metadata['normalized_metadata']['end_date'] == '2023-03-01T00:00:00Z'
        assert metadata_2.json_metadata['normalized_metadata']['enroll_by_date'] == '2023-03-15T00:00:00Z'
        assert metadata_2.json_metadata['normalized_metadata']['enroll_start_date'] == '2023-02-01T00:00:00Z'
        expected_normalized_metadata_by_run = {
            course_run['key']: {
                'start_date': course_run['start'],
                'end_date': course_run['end'],
                'enroll_by_date': course_run['seats'][0]['upgrade_deadline'],
                'enroll_start_date': course_run['enrollment_start'],
                'content_price': course_run['first_enrollable_paid_seat_price'] or DEFAULT_NORMALIZED_PRICE,
            }
            for course_run in metadata_2.json_metadata['course_runs']
        }
        assert metadata_2.json_metadata['normalized_metadata_by_run'] == expected_normalized_metadata_by_run
        assert set(program_data.items()).issubset(set(metadata_2.json_metadata['programs'][0].items()))

        assert metadata_3.json_metadata['aggregation_key'] == f'course:{course_key_3}'
        assert metadata_3.json_metadata['normalized_metadata']['start_date'] == '2023-03-01T00:00:00Z'
        assert metadata_3.json_metadata['normalized_metadata']['end_date'] == '2023-03-01T00:00:00Z'
        assert metadata_3.json_metadata['normalized_metadata']['enroll_by_date'] == '2023-02-01T00:00:00Z'
        assert metadata_3.json_metadata['normalized_metadata']['content_price'] == 90
        expected_normalized_metadata_by_run = {
            course_run['key']: {
                'start_date': course_run['start'],
                'end_date': course_run['end'],
                'enroll_by_date': course_run['seats'][0]['upgrade_deadline'],
                'enroll_start_date': course_run['enrollment_start'],
                'content_price': course_run['first_enrollable_paid_seat_price'] or DEFAULT_NORMALIZED_PRICE,
            }
            for course_run in metadata_3.json_metadata['course_runs']
        }
        assert metadata_3.json_metadata['normalized_metadata_by_run'] == expected_normalized_metadata_by_run

        assert metadata_4.json_metadata['aggregation_key'] == f'course:{course_key_4}'
        assert metadata_4.json_metadata['full_course_only_field'] == 'test_4'
        assert metadata_4.json_metadata['programs'] == []
        assert metadata_4.json_metadata['normalized_metadata'] == {
            'start_date': None,
            'end_date': None,
            'enroll_by_date': None,
            'enroll_start_date': None,
            'content_price': DEFAULT_NORMALIZED_PRICE,
        }

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
        metadata_1.catalog_queries.set([self.catalog_query])
        metadata_2 = ContentMetadataFactory(content_type=PROGRAM, content_key=program_key_2)
        metadata_2.catalog_queries.set([self.catalog_query])

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

    @mock.patch('enterprise_catalog.apps.api.tasks.partition_program_keys_for_indexing')
    @mock.patch('enterprise_catalog.apps.api_client.base_oauth.OAuthAPIClient')
    def test_update_full_metadata_program_dry_run(self, mock_oauth_client, mock_partition_program_keys):
        """
        Assert that during dry run full program metadata is not merged with original json_metadata
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
        metadata_1.catalog_queries.set([self.catalog_query])
        metadata_2 = ContentMetadataFactory(content_type=PROGRAM, content_key=program_key_2)
        metadata_2.catalog_queries.set([self.catalog_query])

        assert metadata_1.json_metadata != program_data_1
        assert metadata_2.json_metadata != program_data_2

        tasks.update_full_content_metadata_task.apply(kwargs={'dry_run': True}).get()

        actual_program_keys_args = mock_partition_program_keys.call_args_list[0][0][0]
        self.assertEqual(set(actual_program_keys_args), {metadata_1, metadata_2})

        metadata_1 = ContentMetadata.objects.get(content_key='02f5edeb-6604-4131-bf45-acd8df91e1f9')
        metadata_2 = ContentMetadata.objects.get(content_key='be810df3-a059-42a7-b11f-d9bfb2877b15')

        # Validate original json_metadata still in place after dry run
        program_data_1.update(metadata_1.json_metadata)
        program_data_2.update(metadata_2.json_metadata)
        program_data_1.update({'aggregation_key': 'program:02f5edeb-6604-4131-bf45-acd8df91e1f9'})
        program_data_2.update({'aggregation_key': 'program:be810df3-a059-42a7-b11f-d9bfb2877b15'})

        assert metadata_1.json_metadata != program_data_1
        assert metadata_2.json_metadata != program_data_2

    # pylint: disable=unused-argument
    @mock.patch('enterprise_catalog.apps.api.tasks.task_recently_run', return_value=False)
    @mock.patch('enterprise_catalog.apps.api.tasks.partition_program_keys_for_indexing')
    @mock.patch('enterprise_catalog.apps.api_client.base_oauth.OAuthAPIClient')
    def test_update_full_metadata_exec_ed(self, mock_oauth_client, mock_partition_course_keys, mock_task_recently_run):
        """
        Assert that all the fields are correctly updated in ContentMetadata records that represent Exec Ed courses.

        Check both things:
        * Make sure the field normalization step caused the creation of expected net-new fields.
        * Make sure the start/end dates are copied from the additional_metadata into the course run dict of the course.
        """
        course_key = 'edX+testX'
        course_run_key = 'course-v1:edX+testX+1'
        course_run_uuid = str(uuid.uuid4())

        # Simulate a course data in the response from /api/v1/courses/
        course_data = {
            'aggregation_key': f'course:{course_key}',
            'key': course_key,
            'course_type': EXEC_ED_2U_COURSE_TYPE,
            'course_runs': [{
                'key': course_run_key,
                'uuid': course_run_uuid,
                # start/end dates are the same across course types
                'start': '2023-03-01T00:00:00Z',
                'end': '2023-04-09T23:59:59Z',
                # `enrollment_end` in place of seat.upgrade_deadline for Exec Ed courses
                'enrollment_end': '2023-02-01T00:00:00Z',
            }],
            'programs': [],
            'entitlements': [
                {
                    'price': 2900,
                    'mode': 'paid-executive-education',
                },
            ],
            'advertised_course_run_uuid': course_run_uuid,

            # Intentionally exclude net-new fields that we will assert are added by the
            # update_full_content_metadata_task.
            #
            # 'normalized_metadata': {
            #     'start_date': '2023-03-01T00:00:00Z',
            #     'end_date': '2023-04-09T23:59:59Z'
            #     'enroll_by_date': '2023-02-01T00:00:00Z',
            #     'content_price': 2900,
            # }
        }

        mock_oauth_client.return_value.get.return_value.status_code = 200

        # Mock out the data that should be returned from discovery's /api/v1/courses endpoint
        mock_oauth_client.return_value.get.return_value.json.side_effect = [
            {'results': [course_data]},
            {'results': []},
        ]
        mock_partition_course_keys.return_value = ([], [],)

        # Simulate a pre-existing ContentMetadata object freshly seeded using the response from /api/v1/search/all/
        course_metadata = ContentMetadataFactory.create(
            content_type=COURSE, content_key=course_key, _json_metadata={
                'aggregation_key': 'course:edX+testX',
                'key': 'edX+testX',
                'course_type': EXEC_ED_2U_COURSE_TYPE,
                'course_runs': [{
                    'key': course_run_key,
                    # start/end dates are the same across course types
                    'start': '2023-03-01T00:00:00Z',
                    'end': '2023-04-09T23:59:59Z',
                    # `enrollment_end` in place of seat.upgrade_deadline for Exec Ed courses
                    'enrollment_end': '2023-02-01T00:00:00Z',
                }],
                'programs': [],

                # `advertised_course_run_uuid` is ONLY in the output of /api/v1/courses/, not /api/v1/search/all/
                # 'advertised_course_run_uuid': course_run_uuid,

                # Intentionally exclude net-new fields that we will assert are added by the
                # update_full_content_metadata_task.
                #
                # 'normalized_metadata': {
                #     'start_date': '2023-03-01T00:00:00Z',
                #     'end_date': '2023-04-09T23:59:59Z'
                #     'enroll_by_date': '2023-02-01T00:00:00Z',
                #     'content_price': 2900,
                # }
            }
        )

        course_metadata.catalog_queries.set([self.catalog_query])

        tasks.update_full_content_metadata_task.apply().get()

        assert ContentMetadata.objects.count() == 1

        # Make sure the field normalization step caused the creation of expected net-new fields.
        course_cm = ContentMetadata.objects.get(content_key=course_key)
        assert course_cm.content_type == COURSE

        assert course_cm.json_metadata['normalized_metadata']['start_date'] == '2023-03-01T00:00:00Z'
        assert course_cm.json_metadata['normalized_metadata']['end_date'] == '2023-04-09T23:59:59Z'
        assert course_cm.json_metadata['normalized_metadata']['enroll_by_date'] == '2023-02-01T00:00:00Z'
        assert course_cm.json_metadata['normalized_metadata']['content_price'] == 2900

        normalized_metadata_by_run = course_cm.json_metadata['normalized_metadata_by_run']
        assert normalized_metadata_by_run[course_run_key]['start_date'] == '2023-03-01T00:00:00Z'
        assert normalized_metadata_by_run[course_run_key]['end_date'] == '2023-04-09T23:59:59Z'
        assert normalized_metadata_by_run[course_run_key]['enroll_by_date'] == '2023-02-01T00:00:00Z'
        assert normalized_metadata_by_run[course_run_key]['content_price'] == 2900

        # Make sure the start/end dates are copied from the additional_metadata into the course run dict of the course.
        # This checks that the dummy 2022 dates are overwritten.
        course_run_json = course_cm.json_metadata.get('course_runs')[0]
        assert course_run_json['uuid'] == course_run_uuid
        assert course_run_json['start'] == '2023-03-01T00:00:00Z'
        assert course_run_json['end'] == '2023-04-09T23:59:59Z'


class IndexEnterpriseCatalogCoursesInAlgoliaTaskTests(TestCase):
    """
    Tests for `index_enterprise_catalog_in_algolia_task`
    """

    ALGOLIA_FIELDS = [
        'key',
        'objectID',
        'academy_uuids',
        'academy_tags',
        'enterprise_customer_uuids',
        'enterprise_catalog_uuids',
        'enterprise_catalog_query_uuids',
        'enterprise_catalog_query_titles',
    ]

    def setUp(self):
        super().setUp()

        # Mock the Spanish translation to avoid OpenAI API calls
        # This mock mimics the actual create_spanish_algolia_object behavior
        def mock_create_spanish_object(obj):
            spanish_obj = obj.copy()
            spanish_obj['objectID'] = f"{obj['objectID']}-es"
            return spanish_obj
        
        self.spanish_mock_patcher = mock.patch(
            'enterprise_catalog.apps.api.tasks.create_spanish_algolia_object',
            side_effect=mock_create_spanish_object
        )
        self.spanish_mock_patcher.start()

        # Set up a catalog, query, and metadata for a course and course associated program
        self.academy = AcademyFactory()
        self.tag1 = self.academy.tags.all()[0]
        self.enterprise_catalog_query = CatalogQueryFactory(uuid=SORTED_QUERY_UUID_LIST[0])
        self.enterprise_catalog_courses = EnterpriseCatalogFactory(catalog_query=self.enterprise_catalog_query)
        self.enterprise_catalog_courses.academies.add(self.academy)
        self.course_metadata_published = ContentMetadataFactory(content_type=COURSE, content_key='course-1')
        self.course_metadata_published.catalog_queries.set([self.enterprise_catalog_query])
        self.course_metadata_published.tags.set([self.tag1])
        self.course_metadata_unpublished = ContentMetadataFactory(content_type=COURSE, content_key='course-2')
        # pylint: disable=protected-access
        self.course_metadata_unpublished._json_metadata.get('course_runs')[0].update({
            'status': 'unpublished',
        })
        self.course_metadata_unpublished.catalog_queries.set([self.enterprise_catalog_query])
        self.course_metadata_unpublished.save()

        # Set up new catalog, query, and metadata for a course run]
        # Testing indexing catalog queries when titles aren't present
        course_run_catalog_query = CatalogQueryFactory(uuid=SORTED_QUERY_UUID_LIST[1], title=None)
        self.enterprise_catalog_course_runs = EnterpriseCatalogFactory(catalog_query=course_run_catalog_query)

        self.course_run_metadata_published = ContentMetadataFactory(
            content_type=COURSE_RUN,
            parent_content_key='course-1',
        )
        self.course_run_metadata_published.catalog_queries.set([course_run_catalog_query])
        self.course_run_metadata_unpublished = ContentMetadataFactory(
            content_type=COURSE_RUN,
            parent_content_key='course-2',
        )
        self.course_run_metadata_unpublished._json_metadata.update({
            'status': 'unpublished',
        })
        self.course_run_metadata_unpublished.catalog_queries.set([course_run_catalog_query])
        self.course_run_metadata_unpublished.save()

        _hydrate_course_normalized_metadata()

    def tearDown(self):
        """Clean up mocks."""
        self.spanish_mock_patcher.stop()
        super().tearDown()

    def _create_expected_spanish_object(self, english_object):
        """
        Create an expected Spanish object from an English object.
        This should mirror the mock behavior of create_spanish_algolia_object.
        
        The Spanish objectID has '-es-' inserted before the batch suffix.
        For example:
        - English: 'course-{uuid}-catalog-uuids-0'
        - Spanish: 'course-{uuid}-es-catalog-uuids-0'
        
        Args:
            english_object (dict): The English Algolia object
            
        Returns:
            dict: The expected Spanish Algolia object
        """
        spanish_object = english_object.copy()
        object_id = english_object['objectID']
        
        # Insert '-es-' before the batch type marker
        # The objectID pattern is: {content-type}-{uuid}-{batch-type}-{batch-subtype}-{batch-number}
        # Where batch-type is one of: catalog, customer
        # And batch-subtype is one of: uuids, query-uuids
        # Result: {content-type}-{uuid}-es-{batch-type}-{batch-subtype}-{batch-number}
        
        # Find the position to insert '-es-' by looking for batch type markers
        batch_markers = ['-catalog-', '-customer-']
        insert_pos = -1
        
        for marker in batch_markers:
            pos = object_id.find(marker)
            if pos != -1:
                insert_pos = pos
                break
        
        if insert_pos != -1:
            # Insert '-es' before the batch marker
            spanish_object['objectID'] = object_id[:insert_pos] + '-es' + object_id[insert_pos:]
        else:
            # Fallback: just append -es if structure is unexpected
            spanish_object['objectID'] = f"{object_id}-es"
        
        return spanish_object

    def _set_up_factory_data_for_algolia(self):
        expected_catalog_uuids = sorted([
            str(self.enterprise_catalog_courses.uuid),
            str(self.enterprise_catalog_course_runs.uuid)
        ])
        expected_customer_uuids = sorted([
            str(self.enterprise_catalog_courses.enterprise_uuid),
            str(self.enterprise_catalog_course_runs.enterprise_uuid),
        ])
        expected_academy_uuids = [str(self.academy.uuid)]
        expected_academy_tags = sorted([self.tag1.title])
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
            'academy_uuids': expected_academy_uuids,
            'academy_tags': expected_academy_tags,
            'query_uuids': query_uuids,
            'query_titles': query_titles,
            'course_metadata_published': self.course_metadata_published,
            'course_metadata_unpublished': self.course_metadata_unpublished,
        }

    def _sort_tags_in_algolia_object_list(self, algolia_obj):
        for obj in algolia_obj:
            if obj.get('academy_tags'):
                obj['academy_tags'] = sorted(obj['academy_tags'])
        return algolia_obj

    def test_add_metadata_to_algolia_objects_skips_metadata_records_over_max_size(self):
        """
        Test that the indexing task will skip adding records into the `algolia_products_by_object_id` list of objects
        that exceed to max byte size according to the Algolia docs.
        """
        algolia_products_by_object_id = {}
        normal_sized_course = ContentMetadataFactory(content_type=COURSE, content_key='test-course-1')
        short_description_string = "ayylmao".join(["" for x in range(50000)])
        full_description_string = "foobar".join(["" for x in range(50000)])
        too_big_sized_course = ContentMetadataFactory(content_type=COURSE, content_key='test-course-2')
        too_big_sized_course._json_metadata.update(  # pylint: disable=protected-access
            {"short_description": short_description_string, "full_description": full_description_string}
        )
        too_big_sized_course.save()
        tasks.add_metadata_to_algolia_objects(
            metadata=too_big_sized_course,
            algolia_products_by_object_id=algolia_products_by_object_id,
            catalog_uuids=[str(uuid.uuid4())],
            customer_uuids=[str(uuid.uuid4())],
            catalog_queries=[(str(uuid.uuid4()), "query title")],
            academy_uuids=[str(uuid.uuid4())],
            academy_tags=[],
            video_ids=[],
        )
        assert not algolia_products_by_object_id
        tasks.add_metadata_to_algolia_objects(
            metadata=normal_sized_course,
            algolia_products_by_object_id=algolia_products_by_object_id,
            catalog_uuids=[str(uuid.uuid4())],
            customer_uuids=[str(uuid.uuid4())],
            catalog_queries=[(str(uuid.uuid4()), "query title")],
            academy_uuids=[str(uuid.uuid4())],
            academy_tags=[],
            video_ids=[],
        )

        for algolia_object_key in algolia_products_by_object_id.keys():
            assert str(normal_sized_course.content_uuid) in algolia_object_key
            assert not str(too_big_sized_course.content_uuid) in algolia_object_key

    def test_get_algolia_objects_from_course_metadata(self):
        """
        Test that the ``get_algolia_objects_from_course_content_metadata`` method generates a set of algolia objects to
        index from a single course content metadata object
        """
        test_course = ContentMetadataFactory(content_type=COURSE, content_key='test-course-1')
        # Create all 5 test catalogs.
        catalog_queries = [CatalogQueryFactory(uuid=uuid.uuid4()) for _ in range(3)]
        catalogs = [
            EnterpriseCatalogFactory(catalog_query=query)
            for query in catalog_queries
        ]

        test_course.catalog_queries.set(catalog_queries[0:3])

        algolia_objects = tasks.get_algolia_objects_from_course_content_metadata(test_course)

        expected_transformed_advertised_course_run = {
            'key': 'course-v1:edX+DemoX+2T2024',
            'pacing_type': None,
            'availability': 'current',
            'start': '2024-02-12T11:00:00Z',
            'end': '2026-02-05T11:00:00Z',
            'min_effort': None,
            'max_effort': None,
            'weeks_to_complete': None,
            'upgrade_deadline': 1769471999.0,
            'enroll_by': 1769471999.0,
            'has_enroll_by': True,
            'enroll_start': None,
            'has_enroll_start': False,
            'content_price': 50.0,
            'is_active': True,
            'is_late_enrollment_eligible': False,
            'restriction_type': None
        }

        # Should look something like-
        #  [{'advertised_course_run': {'availability': 'current',
        #                             'end': None,
        #                             'key': 'course-v1:edX+DemoX',
        #                             'max_effort': None,
        #                             'min_effort': None,
        #                             'pacing_type': None,
        #                             'start': None,
        #                             'upgrade_deadline': 32503680000.0,
        #                             'weeks_to_complete': None},
        #   'aggregation_key': 'course:test-course-1',
        #   'availability': ['Available Now'],
        #   'card_image_url': 'https://picsum.photos/540/209.jpg',
        #   'content_type': 'course',
        #   'course_bayesian_average': 0,
        #   'course_runs': [{'availability': 'current',
        #                    'end': None,
        #                    'key': 'course-v1:edX+DemoX',
        #                    'max_effort': None,
        #                    'min_effort': None,
        #                    'pacing_type': None,
        #                    'start': None,
        #                    'upgrade_deadline': 32503680000.0,
        #                    'weeks_to_complete': None}],
        #   'enterprise_catalog_uuids': ['0bdd57b7-b1cb-4775-b0dc-3cf49ff7d7f2',
        #                                '2b861d68-06d7-415b-9baa-b5f496fafa1a',
        #                                'add4b32e-8b32-4cb3-8de6-956210377330'],
        #   'key': 'test-course-1',
        #   'learning_type': 'course',
        #   'learning_type_v2': 'course',
        #   'marketing_url': 'https://marketing.url/test-course-1',
        #   'objectID': 'course-be9a029e-8990-4f94-bf24-770fece63344-catalog-uuids-0',
        #   'partners': [{'logo_image_url': 'https://dummyimage.com/265x132.jpg',
        #                 'name': 'Partner Name'}],
        #   'program_titles': [],
        #   'programs': [],
        #   'skill_names': [],
        #   'skills': [],
        #   'subjects': [],
        #   'title': 'Fake Content Title UItWeUluIK',
        #   'upcoming_course_runs': 0,
        #   'uuid': 'be9a029e-8990-4f94-bf24-770fece63344'}, ... ]
        for algo_object in algolia_objects:
            assert algo_object.get('key') == test_course.content_key
            assert algo_object.get('uuid') == test_course.json_metadata.get('uuid')
            assert algo_object.get('advertised_course_run') == expected_transformed_advertised_course_run

            if object_catalogs := algo_object.get('enterprise_catalog_uuids'):
                assert set(object_catalogs) == {str(catalog.uuid) for catalog in catalogs}

            if object_customers := algo_object.get('enterprise_customer_uuids'):
                assert set(object_customers) == {str(catalog.enterprise_uuid) for catalog in catalogs}

            if object_queries := algo_object.get('enterprise_catalog_query_uuids'):
                assert set(object_queries) == {str(query.uuid) for query in catalog_queries}

            if object_queries_titles := algo_object.get('enterprise_catalog_query_titles'):
                assert set(object_queries_titles) == {str(query.title) for query in catalog_queries}

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    @override_settings(SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS=True)
    def test_index_algolia_program_common_uuids_only(self, mock_search_client):
        """
        Assert that when a program contains multiple courses, that program only inherits the UUIDs common to all
        contained courses.

        This DAG represents the complete test environment:
        ┌──────────────┐┌──────────────┐┌──────────────┐
        │*test-course-1││*test-course-2││*test-course-3│
        │--------------││--------------││--------------│
        │in catalog-1  ││              ││              │
        │in catalog-2  ││in catalog-2  ││              │
        │in catalog-3  ││in catalog-3  ││in catalog-3  │
        │              ││in catalog-4  ││in catalog-4  │
        │              ││              ││in catalog-5  │
        └┬─────────────┘└┬─────────────┘└┬─────────────┘
        ┌▽───────────────▽───────────────▽─────────────┐
        │*program-1                                    │
        │----------------------------------------------│
        │(should inherit catalog-3 only)               │
        └──────────────────────────────────────────────┘
        * = indexable
        """
        program_1 = ContentMetadataFactory(content_type=PROGRAM, content_key='program-1')
        test_course_1 = ContentMetadataFactory(content_type=COURSE, content_key='test-course-1')
        test_course_2 = ContentMetadataFactory(content_type=COURSE, content_key='test-course-2')
        test_course_3 = ContentMetadataFactory(content_type=COURSE, content_key='test-course-3')

        # Associate three main test courses with the program.
        test_course_1.associated_content_metadata.set([program_1])
        test_course_2.associated_content_metadata.set([program_1])
        test_course_3.associated_content_metadata.set([program_1])

        # Create all 5 test catalogs.
        catalog_queries = [CatalogQueryFactory(uuid=uuid.uuid4()) for _ in range(5)]
        catalogs = [
            EnterpriseCatalogFactory(catalog_query=query)
            for query in catalog_queries
        ]

        # Associate the 5 catalogs to the 3 courses in a staggering fashion.
        test_course_1.catalog_queries.set(catalog_queries[0:3])
        test_course_2.catalog_queries.set(catalog_queries[1:4])
        test_course_3.catalog_queries.set(catalog_queries[2:5])

        test_course_1.save()
        test_course_2.save()
        test_course_3.save()
        _hydrate_course_normalized_metadata()

        actual_algolia_products_sent = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent
            actual_algolia_products_sent = list(products_iterable)
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        products_found_log_records = [record for record in info_logs.output if ' products found.' in record]
        assert ' 30 products found.' in products_found_log_records[0]

        # create expected data to be added/updated in the Algolia index.
        expected_program_1_objects_to_index = []
        program_uuid = program_1.json_metadata.get('uuid')
        expected_program_1_objects_to_index.append({
            'objectID': f'program-{program_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': [str(catalogs[2].uuid)],
            'academy_tags': [],
            'academy_uuids': [],
        })
        expected_program_1_objects_to_index.append({
            'objectID': f'program-{program_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': [str(catalogs[2].enterprise_uuid)],
            'academy_tags': [],
            'academy_uuids': [],
        })
        expected_program_1_objects_to_index.append({
            'objectID': f'program-{program_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': [str(catalog_queries[2].uuid)],
            'enterprise_catalog_query_titles': [catalog_queries[2].title],
            'academy_tags': [],
            'academy_uuids': [],
        })


        # verify replace_all_objects is called with the correct Algolia object data.
        # Create Spanish versions of expected objects
        expected_spanish_objects = [
            self._create_expected_spanish_object(obj) for obj in expected_program_1_objects_to_index
        ]
        expected_all_objects = expected_program_1_objects_to_index + expected_spanish_objects
        
        expected_program_call_args = sorted(expected_all_objects, key=itemgetter('objectID'))
        actual_program_call_args = sorted(
            [
                product for product in actual_algolia_products_sent
                if program_uuid in product['objectID']
            ],
            key=itemgetter('objectID'),
        )
        assert expected_program_call_args == actual_program_call_args

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    @override_settings(SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS=True)
    def test_index_algolia_program_unindexable_content(self, mock_search_client):
        """
        Assert that when a program contains ANY unindexable courses, that program is not indexed for any catalog
        (nuance: IFF no catalog declares the program directly).

        This DAG represents the complete test environment:
        ┌──────────────┐┌──────────────┐┌──────────────┐
        │*test-course-1││*test-course-2││*test-course-3│
        │--------------││--------------││--------------│
        │in catalog-1  ││              ││              │
        │in catalog-2  ││in catalog-2  ││              │
        │in catalog-3  ││in catalog-3  ││in catalog-3  │
        │              ││in catalog-4  ││in catalog-4  │┌────────┐
        │              ││              ││in catalog-5  ││course-2│
        └┬─────────────┘└┬─────────────┘└┬─────────────┘└─┬──────┘
        ┌▽───────────────▽───────────────▽────────────────▽┐
        │*program-1                                        │
        │--------------------------------------------------│
        │(program should not be indexed)                   │
        └──────────────────────────────────────────────────┘
        * = indexable
        """
        program_1 = ContentMetadataFactory(content_type=PROGRAM, content_key='program-1')
        test_course_1 = ContentMetadataFactory(content_type=COURSE, content_key='test-course-1')
        test_course_2 = ContentMetadataFactory(content_type=COURSE, content_key='test-course-2')
        test_course_3 = ContentMetadataFactory(content_type=COURSE, content_key='test-course-3')

        # Associate three main test courses with the program.
        test_course_1.associated_content_metadata.set([program_1])
        test_course_2.associated_content_metadata.set([program_1])
        test_course_3.associated_content_metadata.set([program_1])
        # Also throw in the unpublished (unindexable) course to cause the program to fail to be indexed.
        self.course_metadata_unpublished.associated_content_metadata.set([program_1])

        # Create all 5 test catalogs.
        catalog_queries = [CatalogQueryFactory(uuid=uuid.uuid4()) for _ in range(5)]
        _ = [
            EnterpriseCatalogFactory(catalog_query=query)
            for query in catalog_queries
        ]

        # Associate the 5 catalogs to the 3 courses in a staggering fashion.
        test_course_1.catalog_queries.set(catalog_queries[0:3])
        test_course_2.catalog_queries.set(catalog_queries[1:4])
        test_course_3.catalog_queries.set(catalog_queries[2:5])

        test_course_1.save()
        test_course_2.save()
        test_course_3.save()
        _hydrate_course_normalized_metadata()

        actual_algolia_products_sent = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent
            actual_algolia_products_sent = list(products_iterable)
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        products_found_log_records = [record for record in info_logs.output if ' products found.' in record]
        # count should be "9 products found", 5 additional products are from the test course in self.setUp()
        assert ' 24 products found.' in products_found_log_records[0]

        # assert the program was not indexed.
        program_uuid = program_1.json_metadata.get('uuid')
        assert all(program_uuid not in product['objectID'] for product in actual_algolia_products_sent)

    def test_index_content_keys_in_algolia(self):
        """
        Test the _index_content_keys_in_algolia helper function to make sure it creates a generator to support batching
        correctly.
        """
        test_content_keys = [
            'course-v1:edX+testX+0',
            'course-v1:edX+testX+1',
            'course-v1:edX+testX+2',
            'course-v1:edX+testX+3',
            'course-v1:edX+testX+4',
        ]

        actual_algolia_products_sent_sequence = None

        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent_sequence
            actual_algolia_products_sent_sequence = list(products_iterable)
        mock_algolia_client = mock.MagicMock()
        mock_algolia_client.replace_all_objects.side_effect = mock_replace_all_objects

        # pylint: disable=unused-argument
        def mock_get_algolia_products_for_batch(
            batch_num,
            content_keys_batch,
            all_indexable_content_keys,
            program_to_courses_courseruns_mapping,
            pathway_to_programs_courses_mapping,
            context_accumulator,
            dry_run=False,
        ):
            return [{'key': content_key, 'foo': 'bar'} for content_key in content_keys_batch]

        with mock.patch(
            'enterprise_catalog.apps.api.tasks._get_algolia_products_for_batch',
            side_effect=mock_get_algolia_products_for_batch,
        ):
            with mock.patch('enterprise_catalog.apps.api.tasks.REINDEX_TASK_BATCH_SIZE', 2):
                # pylint: disable=protected-access
                tasks._index_content_keys_in_algolia(test_content_keys, mock_algolia_client)

        assert actual_algolia_products_sent_sequence == [
            {'key': 'course-v1:edX+testX+0', 'foo': 'bar'},
            {'key': 'course-v1:edX+testX+1', 'foo': 'bar'},
            {'key': 'course-v1:edX+testX+2', 'foo': 'bar'},
            {'key': 'course-v1:edX+testX+3', 'foo': 'bar'},
            {'key': 'course-v1:edX+testX+4', 'foo': 'bar'},
        ]

    @mock.patch('enterprise_catalog.apps.catalog.algolia_utils.SearchClient')
    def test_delete_indices_exception_handling(self, mock_search_client):
        """
        Test that exceptions during index deletion are properly caught and re-raised.
        """
        # Setup mock data
        index_name = 'enterprise_catalog_tmp_test'
        mock_indices = [index_name]

        # Configure mock
        mock_client = mock.MagicMock()
        mock_index = mock.MagicMock()
        mock_index.delete.side_effect = Exception("Test exception")
        mock_client.init_index.return_value = mock_index
        mock_search_client.create.return_value = mock_client

        # Create a mock task instance
        mock_task_id = uuid.uuid4()
        bound_task_object = mock.MagicMock()
        bound_task_object.request.id = mock_task_id

        # Test that the exception is re-raised
        with self.assertRaises(Exception):
            with self.assertLogs(level='ERROR') as log_context:
                tasks._delete_indices(mock_client, mock_indices, dry_run=False)  # pylint: disable=protected-access

        # Verify the exception was logged
        self.assertTrue(any('Test exception' in msg for msg in log_context.output))

        # Verify the client was initialized with the correct index
        mock_client.init_index.assert_called_once_with(index_name)

    # Test remove_old_temporary_catalog_indices_task
    @mock.patch('enterprise_catalog.apps.catalog.algolia_utils.SearchClient')
    def test_remove_old_temporary_catalog_indices(self, mock_search_client):
        """
        Test that temporary indices between 10 and 60 days old get deleted.
        """
        # Setup mock data
        now = datetime.now()
        index_name = 'enterprise_catalog_new'
        # Mock django conf settings.ALGOLIA['INDEX_NAME'] to be 'enterprise_catalog_new'
        with self.settings(ALGOLIA={'INDEX_NAME': index_name}):

            mock_indices = {
                'items': [
                    # Should be included (30 days old)
                    {
                        'name': f'{index_name}_tmp_1',
                        'updatedAt': (now - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                        'entries': 0
                    },
                    # Should be included (10 days old)
                    {
                        'name': f'{index_name}_tmp_7',
                        'updatedAt': (now - timedelta(days=10)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                        'entries': 0
                    },
                    # Should be included (15 days old)
                    {
                        'name': f'{index_name}_tmp_2',
                        'updatedAt': (now - timedelta(days=15)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                        'entries': 0
                    },
                    # # Should be included (has entries)
                    {
                        'name': f'{index_name}_tmp_6',
                        'updatedAt': (now - timedelta(days=15)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                        'entries': 1
                    },
                    # Should not be included (5 days old)
                    {
                        'name': f'{index_name}_tmp_3',
                        'updatedAt': (now - timedelta(days=5)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                        'entries': 0
                    },
                    # Should not be included (65 days old)
                    {
                        'name': f'{index_name}_tmp_4',
                        'updatedAt': (now - timedelta(days=65)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                        'entries': 0
                    },
                    # Should not be included (not a tmp index)
                    {
                        'name': index_name,
                        'updatedAt': (now - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                        'entries': 0
                    },
                    # Should not be included (no creation date)
                    {
                        'name': f'{index_name}_tmp_5',
                        'entries': 0
                    },
                ]
            }

            # Configure mock
            mock_client = mock.MagicMock()
            mock_client.list_indices.return_value = mock_indices
            mock_search_client.create.return_value = mock_client

            # Create a mock task instance (similar to other tests in the file)
            mock_task_id = uuid.uuid4()
            bound_task_object = mock.MagicMock()
            bound_task_object.request.id = mock_task_id
            bound_task_object.request.args = ()
            bound_task_object.request.kwargs = {}

            with self.assertLogs(level='INFO'):
                # Call the task with the bound task object
                tasks.remove_old_temporary_catalog_indices_task(
                    bound_task_object, min_days_ago=10, max_days_ago=60, dry_run=False
                )

                # Verify the correct indices were identified
                expected_indices_to_delete = [
                    f'{index_name}_tmp_1',
                    f'{index_name}_tmp_2',
                    f'{index_name}_tmp_6',
                    f'{index_name}_tmp_7'
                ]

                # Verify SearchClient was created with correct credentials
                mock_search_client.create.assert_called_once()

                # Test that mock_search_client.init_index was called with the index names to be deleted and none other
                mock_client.init_index.assert_has_calls(
                    [mock.call(index_name) for index_name in expected_indices_to_delete],
                    any_order=True
                )

                indexes_not_to_delete = [
                    index['name'] for index in mock_indices['items']
                    if index['name'] not in expected_indices_to_delete
                ]

                # Test that mock_search_client.init_index has no calls for indices that should not be deleted
                for call in mock_client.init_index.call_args_list:
                    index_name = call[0][0]
                    assert index_name not in indexes_not_to_delete, f"Unexpected call to delete index: {index_name}"

                assert mock_client.init_index.called

                assert mock_client.init_index.return_value.delete.call_count == len(expected_indices_to_delete)

    # Test remove_old_temporary_catalog_indices_task
    @mock.patch('enterprise_catalog.apps.catalog.algolia_utils.SearchClient')
    def test_remove_old_temporary_catalog_indices_should_not_delete_on_dry_run(self, mock_search_client):
        """
        Test that temporary indices between 10 and 60 days old get deleted.
        """
        # Setup mock data
        now = datetime.now()
        index_name = 'enterprise_catalog_new'
        # Mock django conf settings.ALGOLIA['INDEX_NAME'] to be 'enterprise_catalog_new'
        with self.settings(ALGOLIA={'INDEX_NAME': index_name}):
            mock_indices = {
                'items': [
                    {
                        'name': f'{index_name}_tmp_1',
                        'updatedAt': (now - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                        'entries': 0
                    }
                ]
            }

            # Configure mock
            mock_client = mock.MagicMock()
            mock_client.list_indices.return_value = mock_indices
            mock_search_client.create.return_value = mock_client

            # Create a mock task instance (similar to other tests in the file)
            mock_task_id = uuid.uuid4()
            bound_task_object = mock.MagicMock()
            bound_task_object.request.id = mock_task_id
            bound_task_object.request.args = ()
            bound_task_object.request.kwargs = {}

            with self.assertLogs(level='INFO') as log_context:
                # Call the task with the bound task object
                tasks.remove_old_temporary_catalog_indices_task(
                    bound_task_object, min_days_ago=10, max_days_ago=60
                )

                log_message = [msg for msg in log_context.output if 'Index names to delete' in msg][0]
                self.assertIn(f'{index_name}_tmp_1', log_message)

                # Verify SearchClient was created with correct credentials
                mock_search_client.create.assert_called_once()

                assert not mock_client.init_index.called
                assert not mock_client.init_index.return_value.delete.called

    @mock.patch('enterprise_catalog.apps.api.tasks.new_search_client_or_error')
    def test_remove_old_temporary_catalog_indices_task_client_exception(self, mock_client_or_error):
        """
        Test that client creation exceptions in remove_old_temporary_catalog_indices_task
        are properly caught and re-raised.
        """
        # Test client creation exception
        algolia_exception = AlgoliaException("Test Algolia exception")
        mock_client_or_error.side_effect = algolia_exception

        # Create a mock task instance
        mock_task_id = uuid.uuid4()
        bound_task_object = mock.MagicMock()
        bound_task_object.request.id = mock_task_id
        bound_task_object.request.args = ()
        bound_task_object.request.kwargs = {}

        with self.assertRaises(AlgoliaException) as context:
            with self.assertLogs(level='ERROR') as log_context:
                tasks.remove_old_temporary_catalog_indices_task(bound_task_object, dry_run=True)

        # Verify the exception was logged and re-raised
        self.assertEqual(context.exception, algolia_exception)
        self.assertTrue(any('Creating Algolia client failed' in msg for msg in log_context.output))
        self.assertTrue(any('Test Algolia exception' in msg for msg in log_context.output))

    @mock.patch('enterprise_catalog.apps.api.tasks.new_search_client_or_error')
    @mock.patch('enterprise_catalog.apps.api.tasks._retrieve_inactive_tmp_indices')
    def test_remove_old_temporary_catalog_indices_task_retrieve_exception(
        self, mock_retrieve_indices, mock_client_or_error
    ):
        """
        Test that retrieve indices exceptions in remove_old_temporary_catalog_indices_task
        are properly caught and re-raised.
        """
        # Configure mock for successful client creation
        mock_client = mock.MagicMock()
        mock_client_or_error.return_value = mock_client

        # Test retrieve indices exception
        retrieve_exception = Exception("Test retrieve exception")
        mock_retrieve_indices.side_effect = retrieve_exception

        # Create a mock task instance
        mock_task_id = uuid.uuid4()
        bound_task_object = mock.MagicMock()
        bound_task_object.request.id = mock_task_id
        bound_task_object.request.args = ()
        bound_task_object.request.kwargs = {}

        # This flag will help us detect if the exception was properly re-raised
        exception_was_raised = False

        try:
            with self.assertLogs(level='ERROR') as log_context:
                tasks.remove_old_temporary_catalog_indices_task(bound_task_object, dry_run=True)
        except Exception as e:  # pylint: disable=broad-except
            exception_was_raised = True
            # Verify it's the same exception that was raised
            self.assertEqual(str(e), "Test retrieve exception")

        # Explicitly verify that the exception was re-raised
        self.assertTrue(
            exception_was_raised,
            "The exception was not re-raised. If you removed the 're-raise' line, this test should fail."
        )

        # Verify the exception was logged
        self.assertTrue(any('Retrieving old tmp indices from Algolia failed' in msg for msg in log_context.output))
        self.assertTrue(any('Test retrieve exception' in msg for msg in log_context.output))

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    @override_settings(SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS=True)
    def test_index_algolia_published_course_to_program(self, mock_search_client):
        """
        Assert that only only "indexable" objects are indexed, particularly when an unpublished course is associated
        with a program.

        This DAG represents the complete test environment:
        ┌─────────────┐         ┌────────┐
        │*course-1    │         │course-2│
        └┬───────────┬┘         └────────┘
        ┌▽─────────┐┌▽────────┐
        │*program-1││program-2│
        └──────────┘└─────────┘
        * = indexable
        """
        algolia_data = self._set_up_factory_data_for_algolia()

        program_1 = ContentMetadataFactory(content_type=PROGRAM, content_key='program-1')
        program_2 = ContentMetadataFactory(content_type=PROGRAM, content_key='program-2')

        # Make program-2 hidden to make it "non-indexable". Later we will assert that it will not get indexed.
        program_2._json_metadata.update({  # pylint: disable=protected-access
            'hidden': True,
        })
        program_2.save()

        # Associate published course with a published program and also an unpublished program.
        self.course_metadata_published.associated_content_metadata.set([program_1, program_2])

        actual_algolia_products_sent = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent
            actual_algolia_products_sent = list(products_iterable)
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        products_found_log_records = [record for record in info_logs.output if ' products found.' in record]
        assert ' 12 products found.' in products_found_log_records[0]

        # create expected data to be added/updated in the Algolia index.
        expected_course_1_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': algolia_data['catalog_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': algolia_data['customer_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted(algolia_data['query_uuids']),
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })

        expected_program_1_objects_to_index = []
        program_uuid = program_1.json_metadata.get('uuid')
        expected_program_1_objects_to_index.append({
            'objectID': f'program-{program_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': algolia_data['catalog_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_program_1_objects_to_index.append({
            'objectID': f'program-{program_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': algolia_data['customer_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_program_1_objects_to_index.append({
            'objectID': f'program-{program_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted(algolia_data['query_uuids']),
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })

        expected_algolia_objects_to_index = (
            expected_course_1_objects_to_index
            + expected_program_1_objects_to_index
        )

        # verify replace_all_objects is called with the correct Algolia object data.
        # Create Spanish versions of expected objects
        expected_spanish_objects = [
            self._create_expected_spanish_object(obj) for obj in expected_algolia_objects_to_index
        ]
        expected_all_objects = expected_algolia_objects_to_index + expected_spanish_objects
        
        expected_call_args = sorted(expected_all_objects, key=itemgetter('objectID'))
        actual_call_args = sorted(actual_algolia_products_sent, key=itemgetter('objectID'))
        assert expected_call_args == self._sort_tags_in_algolia_object_list(actual_call_args)

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    @override_settings(SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS=True)
    def test_index_algolia_unpublished_course_to_program(self, mock_search_client):
        """
        Assert that only only "indexable" objects are indexed, particularly when an unpublished course is associated
        with a program.

        This DAG represents the complete test environment:
        ┌─────────────┐          ┌─────────┐
        │course-2     │          │*course-1│
        └┬───────────┬┘          └─────────┘
        ┌▽─────────┐┌▽────────┐
        │*program-1││program-2│
        └──────────┘└─────────┘
        * = indexable
        """
        algolia_data = self._set_up_factory_data_for_algolia()

        program_1 = ContentMetadataFactory(content_type=PROGRAM, content_key='program-1')
        program_2 = ContentMetadataFactory(content_type=PROGRAM, content_key='program-2')

        # Include both test programs into a catalog query so that absence of catalog queries doesn't taint the test
        # (which would prevent indexability).
        program_1.catalog_queries.set([self.enterprise_catalog_query])
        program_2.catalog_queries.set([self.enterprise_catalog_query])

        # Make program-2 hidden to make it "non-indexable". Later we will assert that it will not get indexed.
        program_2._json_metadata.update({  # pylint: disable=protected-access
            'hidden': True,
        })
        program_2.save()

        # Associate unpublished course with a published program and also an unpublished program.
        self.course_metadata_unpublished.associated_content_metadata.set([program_1, program_2])

        actual_algolia_products_sent = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent
            actual_algolia_products_sent = list(products_iterable)
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        products_found_log_records = [record for record in info_logs.output if ' products found.' in record]
        assert ' 12 products found.' in products_found_log_records[0]

        # create expected data to be added/updated in the Algolia index.
        expected_course_1_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': algolia_data['catalog_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': algolia_data['customer_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted(algolia_data['query_uuids']),
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })

        expected_program_1_objects_to_index = []
        program_uuid = program_1.json_metadata.get('uuid')
        expected_program_1_objects_to_index.append({
            'objectID': f'program-{program_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': [str(self.enterprise_catalog_courses.uuid)],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })
        expected_program_1_objects_to_index.append({
            'objectID': f'program-{program_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': [str(self.enterprise_catalog_courses.enterprise_uuid)],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })
        expected_program_1_objects_to_index.append({
            'objectID': f'program-{program_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': [str(self.enterprise_catalog_courses.catalog_query.uuid)],
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })

        expected_algolia_objects_to_index = (
            expected_course_1_objects_to_index
            + expected_program_1_objects_to_index
        )

        # verify replace_all_objects is called with the correct Algolia object data.
        # Create Spanish versions of expected objects
        expected_spanish_objects = [
            self._create_expected_spanish_object(obj) for obj in expected_algolia_objects_to_index
        ]
        expected_all_objects = expected_algolia_objects_to_index + expected_spanish_objects
        
        expected_call_args = sorted(expected_all_objects, key=itemgetter('objectID'))
        actual_call_args = sorted(actual_algolia_products_sent, key=itemgetter('objectID'))
        assert expected_call_args == self._sort_tags_in_algolia_object_list(actual_call_args)

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    @override_settings(SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS=True)
    def test_index_algolia_published_course_to_pathway(self, mock_search_client,):
        """
        Assert that only only "indexable" objects are indexed, particularly when a published course is associated with a
        pathway.

        This DAG represents the complete test environment:
        ┌─────────┐   ┌────────┐
        │*course-1│   │course-2│
        └┬────────┘   └────────┘
        ┌▽─────────┐
        │*pathway-1│
        └──────────┘
        * = indexable
        """
        algolia_data = self._set_up_factory_data_for_algolia()

        pathway_1 = ContentMetadataFactory(content_type=LEARNER_PATHWAY, content_key='pathway-1')

        # Associate published course with a pathway.
        self.course_metadata_published.associated_content_metadata.set([pathway_1])

        actual_algolia_products_sent = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent
            actual_algolia_products_sent = list(products_iterable)
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        products_found_log_records = [record for record in info_logs.output if ' products found.' in record]
        assert ' 12 products found.' in products_found_log_records[0]

        # create expected data to be added/updated in the Algolia index.
        expected_course_1_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': algolia_data['catalog_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': algolia_data['customer_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted(algolia_data['query_uuids']),
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })

        expected_pathway_1_objects_to_index = []
        pathway_uuid = pathway_1.json_metadata.get('uuid')
        expected_pathway_1_objects_to_index.append({
            'key': pathway_1.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': algolia_data['catalog_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_pathway_1_objects_to_index.append({
            'key': pathway_1.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': algolia_data['customer_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_pathway_1_objects_to_index.append({
            'key': pathway_1.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted(algolia_data['query_uuids']),
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })

        expected_algolia_objects_to_index = (
            expected_course_1_objects_to_index
            + expected_pathway_1_objects_to_index
        )

        # verify replace_all_objects is called with the correct Algolia object data.
        # Create Spanish versions of expected objects
        expected_spanish_objects = [
            self._create_expected_spanish_object(obj) for obj in expected_algolia_objects_to_index
        ]
        expected_all_objects = expected_algolia_objects_to_index + expected_spanish_objects
        
        expected_call_args = sorted(expected_all_objects, key=itemgetter('objectID'))
        actual_call_args = sorted(actual_algolia_products_sent, key=itemgetter('objectID'))
        assert expected_call_args == self._sort_tags_in_algolia_object_list(actual_call_args)

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    @override_settings(SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS=True)
    def test_index_algolia_unpublished_course_to_pathway(self, mock_search_client):
        """
        Assert that only only "indexable" objects are indexed, particularly when an unpublished course is associated
        with a pathway.

        This DAG represents the complete test environment:
        ┌────────┐     ┌─────────┐
        │course-2│     │*course-1│
        └┬───────┘     └─────────┘
        ┌▽─────────┐
        │*pathway-1│
        └──────────┘
        * = indexable
        """
        algolia_data = self._set_up_factory_data_for_algolia()

        pathway_1 = ContentMetadataFactory(content_type=LEARNER_PATHWAY, content_key='pathway-1')

        # Include pathway into a catalog query so that absence of a catalog query doesn't taint the test
        # (which would prevent indexability of the pathway).
        pathway_1.catalog_queries.set([self.enterprise_catalog_query])

        # Associate unpublished course with a pathway.
        self.course_metadata_unpublished.associated_content_metadata.set([pathway_1])

        actual_algolia_products_sent = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent
            actual_algolia_products_sent = list(products_iterable)
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        products_found_log_records = [record for record in info_logs.output if ' products found.' in record]
        assert ' 12 products found.' in products_found_log_records[0]

        # create expected data to be added/updated in the Algolia index.
        expected_course_1_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': algolia_data['catalog_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': algolia_data['customer_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted(algolia_data['query_uuids']),
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })

        expected_pathway_1_objects_to_index = []
        pathway_uuid = pathway_1.json_metadata.get('uuid')
        expected_pathway_1_objects_to_index.append({
            'key': pathway_1.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': [str(self.enterprise_catalog_courses.uuid)],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })
        expected_pathway_1_objects_to_index.append({
            'key': pathway_1.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': [str(self.enterprise_catalog_courses.enterprise_uuid)],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })
        expected_pathway_1_objects_to_index.append({
            'key': pathway_1.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': [str(self.enterprise_catalog_courses.catalog_query.uuid)],
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })

        expected_algolia_objects_to_index = (
            expected_course_1_objects_to_index
            + expected_pathway_1_objects_to_index
        )

        # verify replace_all_objects is called with the correct Algolia object data.
        # Create Spanish versions of expected objects
        expected_spanish_objects = [
            self._create_expected_spanish_object(obj) for obj in expected_algolia_objects_to_index
        ]
        expected_all_objects = expected_algolia_objects_to_index + expected_spanish_objects
        
        expected_call_args = sorted(expected_all_objects, key=itemgetter('objectID'))
        actual_call_args = sorted(actual_algolia_products_sent, key=itemgetter('objectID'))
        assert expected_call_args == self._sort_tags_in_algolia_object_list(actual_call_args)

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    @override_settings(SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS=True)
    def test_index_algolia_program_to_pathway(self, mock_search_client):
        """
        Assert that only only "indexable" objects are indexed, particularly when a hidden, and non-hidden program is
        associated with a pathway.

        This DAG represents the complete test environment:
        ┌──────────┐┌─────────┐  ┌─────────┐┌────────┐
        │*program-1││program-2│  │*course-1││course-2│
        └┬─────────┘└┬────────┘  └─────────┘└────────┘
        ┌▽───────────▽┐
        │*pathway-1   │
        └─────────────┘
        * = indexable
        """
        algolia_data = self._set_up_factory_data_for_algolia()

        program_1 = ContentMetadataFactory(content_type=PROGRAM, content_key='program-1')
        program_2 = ContentMetadataFactory(content_type=PROGRAM, content_key='program-2')
        pathway_1 = ContentMetadataFactory(content_type=LEARNER_PATHWAY, content_key='pathway-1')

        # Include both programs into a catalog query so that absence of a catalog query doesn't taint the test
        # (which would prevent indexability of the programs).
        program_1.catalog_queries.set([self.enterprise_catalog_query])
        program_1.catalog_queries.set([self.enterprise_catalog_query])

        # Make program-2 hidden to make it "non-indexable". Later we will assert that it will not get indexed.
        program_2._json_metadata.update({  # pylint: disable=protected-access
            'hidden': True,
        })
        program_2.save()

        # Associate both programs with the pathway.
        program_1.associated_content_metadata.set([pathway_1])
        program_2.associated_content_metadata.set([pathway_1])

        actual_algolia_products_sent = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent
            actual_algolia_products_sent = list(products_iterable)
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        products_found_log_records = [record for record in info_logs.output if ' products found.' in record]
        assert ' 18 products found.' in products_found_log_records[0]

        # create expected data to be added/updated in the Algolia index.
        expected_course_1_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': algolia_data['catalog_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': algolia_data['customer_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_course_1_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted(algolia_data['query_uuids']),
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })

        expected_program_1_objects_to_index = []
        program_uuid = program_1.json_metadata.get('uuid')
        expected_program_1_objects_to_index.append({
            'objectID': f'program-{program_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': [str(self.enterprise_catalog_courses.uuid)],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })
        expected_program_1_objects_to_index.append({
            'objectID': f'program-{program_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': [str(self.enterprise_catalog_courses.enterprise_uuid)],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })
        expected_program_1_objects_to_index.append({
            'objectID': f'program-{program_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': [str(self.enterprise_catalog_courses.catalog_query.uuid)],
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })

        expected_pathway_1_objects_to_index = []
        pathway_uuid = pathway_1.json_metadata.get('uuid')
        expected_pathway_1_objects_to_index.append({
            'key': pathway_1.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': [str(self.enterprise_catalog_courses.uuid)],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })
        expected_pathway_1_objects_to_index.append({
            'key': pathway_1.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': [str(self.enterprise_catalog_courses.enterprise_uuid)],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })
        expected_pathway_1_objects_to_index.append({
            'key': pathway_1.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': [str(self.enterprise_catalog_courses.catalog_query.uuid)],
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })

        expected_algolia_objects_to_index = (
            expected_course_1_objects_to_index
            + expected_program_1_objects_to_index
            + expected_pathway_1_objects_to_index
        )

        # verify replace_all_objects is called with the correct Algolia object data.
        # Create Spanish versions of expected objects
        expected_spanish_objects = [
            self._create_expected_spanish_object(obj) for obj in expected_algolia_objects_to_index
        ]
        expected_all_objects = expected_algolia_objects_to_index + expected_spanish_objects
        
        expected_call_args = sorted(expected_all_objects, key=itemgetter('objectID'))
        actual_call_args = sorted(actual_algolia_products_sent, key=itemgetter('objectID'))
        assert expected_call_args == self._sort_tags_in_algolia_object_list(actual_call_args)

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    @override_settings(SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS=True)
    # pylint: disable=protected-access
    def test_index_algolia_restricted_runs_mixed_course(self, mock_search_client):
        """
        Assert that the correct data is sent to Algolia index, with the expected enterprise
        catalog and enterprise customer associations *with restricted runs in the picture*.

        This DAG represents the complete test environment:

        ┌────────────────────────────────────┐
        │ self.course_run_metadata_published │
        └┬───────────────────────────────────┘
         | ┌────────────────────────────────────┐
         | │ courserun_restricted_for_catalog_A │
         | └┬───────────────────────────────────┘
         |  | ┌────────────────────────────────────┐
         |  | │ courserun_restricted_for_catalog_B │
         |  | └┬───────────────────────────────────┘
         |  |  |
        ┌▽──▽──▽─────────────────────────┐
        │ self.course_metadata_published │
        └────────────────────────────────┘
        """
        self.maxDiff = None
        algolia_data = self._set_up_factory_data_for_algolia()

        catalog_A = EnterpriseCatalogFactory()
        catalog_B = EnterpriseCatalogFactory()

        self.course_metadata_published.catalog_queries.set([
            self.enterprise_catalog_query,
            catalog_A.catalog_query,
            catalog_B.catalog_query,
        ])

        # Disconnect the standard course run from any catalog query to make
        # this test simpler and more consistent with the real world (in the
        # real world, runs are not usually associated with any catalog queries
        # directly).
        self.course_run_metadata_published.catalog_queries.set([])

        # Create the ContentMetadata objects for each restricted run.
        courserun_restricted_for_catalog_A = ContentMetadataFactory(
            content_type=COURSE_RUN,
            content_key='courserun_restricted_for_catalog_A',
            parent_content_key=self.course_metadata_published.content_key,
        )
        courserun_restricted_for_catalog_B = ContentMetadataFactory(
            content_type=COURSE_RUN,
            content_key='courserun_restricted_for_catalog_B',
            parent_content_key=self.course_metadata_published.content_key,
        )

        # Update the content filters of each catalog query to explicitly allow
        # their respective restricted runs.
        catalog_A.catalog_query.content_filter.update({
            'restricted_runs_allowed': {
                f'course:{self.course_metadata_published.content_key}': [
                    courserun_restricted_for_catalog_A.content_key,
                ]
            }
        })
        catalog_A.catalog_query.save()
        catalog_B.catalog_query.content_filter.update({
            'restricted_runs_allowed': {
                f'course:{self.course_metadata_published.content_key}': [
                    courserun_restricted_for_catalog_B.content_key,
                ]
            }
        })
        catalog_B.catalog_query.save()

        # Create the RestrictedCourseMetadata objects, respresenting different
        # views of the same course from the perspective of different catalog
        # queries.
        restricted_course_for_catalog_A = RestrictedCourseMetadataFactory(
            content_type=COURSE,
            content_key=self.course_metadata_published.content_key,
            unrestricted_parent=self.course_metadata_published,
            catalog_query=catalog_A.catalog_query,
            _json_metadata=self.course_metadata_published._json_metadata | {
                'advertised_course_run_uuid': courserun_restricted_for_catalog_A.content_uuid,
                'foobar': 'override metadata from restricted_course_for_catalog_A',
            },
        )
        restricted_course_for_catalog_A._json_metadata['course_runs'].append(
            courserun_restricted_for_catalog_A._json_metadata,
        )
        restricted_course_for_catalog_B = RestrictedCourseMetadataFactory(
            content_type=COURSE,
            content_key=self.course_metadata_published.content_key,
            unrestricted_parent=self.course_metadata_published,
            catalog_query=catalog_B.catalog_query,
            _json_metadata=self.course_metadata_published._json_metadata | {
                'advertised_course_run_uuid': courserun_restricted_for_catalog_B.content_uuid,
                'foobar': 'override metadata from restricted_course_for_catalog_B',
            },
        )
        restricted_course_for_catalog_B._json_metadata['course_runs'].append(
            courserun_restricted_for_catalog_B._json_metadata,
        )

        # Create the "canonical" restricted course.  This is a convenience
        # record for simplifying algolia indexing.
        restricted_course_canonical = RestrictedCourseMetadataFactory(
            content_type=COURSE,
            content_key=self.course_metadata_published.content_key,
            unrestricted_parent=self.course_metadata_published,
            catalog_query=None,
            _json_metadata=self.course_metadata_published._json_metadata | {
                'advertised_course_run_uuid': courserun_restricted_for_catalog_B.content_uuid,
                'foobar': 'override metadata from restricted_course_canonical',
            },
        )
        restricted_course_canonical._json_metadata['course_runs'].extend([
            courserun_restricted_for_catalog_A._json_metadata,
            courserun_restricted_for_catalog_B._json_metadata,
        ])

        # Finally, connect all the restricted runs to their correct
        # RestrictedCourseMetadata objects. This association is only read by
        # the algolia indexing logic to determine the catalog queries
        # associated with a unicorn course.
        RestrictedRunAllowedForRestrictedCourseFactory(
            course=restricted_course_for_catalog_A,
            run=courserun_restricted_for_catalog_A,
        )
        RestrictedRunAllowedForRestrictedCourseFactory(
            course=restricted_course_for_catalog_B,
            run=courserun_restricted_for_catalog_B,
        )

        actual_algolia_products_sent = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent
            actual_algolia_products_sent = list(products_iterable)
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS + ['foobar']):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        products_found_log_records = [record for record in info_logs.output if ' products found.' in record]
        assert ' 6 products found.' in products_found_log_records[0]

        # create expected data to be added/updated in the Algolia index.
        expected_algolia_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': sorted([
                str(self.enterprise_catalog_courses.uuid),
                str(catalog_A.uuid),
                str(catalog_B.uuid),
            ]),
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
            'foobar': 'override metadata from restricted_course_canonical',
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': sorted([
                str(self.enterprise_catalog_courses.enterprise_uuid),
                str(catalog_A.enterprise_uuid),
                str(catalog_B.enterprise_uuid),
            ]),
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
            'foobar': 'override metadata from restricted_course_canonical',
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted([
                str(self.enterprise_catalog_courses.catalog_query.uuid),
                str(catalog_A.catalog_query.uuid),
                str(catalog_B.catalog_query.uuid),
            ]),
            'enterprise_catalog_query_titles': sorted([
                self.enterprise_catalog_courses.catalog_query.title,
                catalog_A.catalog_query.title,
                catalog_B.catalog_query.title,
            ]),
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
            'foobar': 'override metadata from restricted_course_canonical',
        })

        # Verify replace_all_objects is called with the correct Algolia object data.
        # Create Spanish versions of expected objects
        expected_spanish_objects = [
            self._create_expected_spanish_object(obj) for obj in expected_algolia_objects_to_index
        ]
        expected_all_objects = expected_algolia_objects_to_index + expected_spanish_objects
        
        expected_call_args = sorted(expected_all_objects, key=itemgetter('objectID'))
        actual_call_args = sorted(actual_algolia_products_sent, key=itemgetter('objectID'))
        assert expected_call_args == self._sort_tags_in_algolia_object_list(actual_call_args)

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    @override_settings(SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS=True)
    # pylint: disable=protected-access
    def test_index_algolia_restricted_runs_unicorn_course(self, mock_search_client):
        """
        Assert that the correct data is sent to Algolia index, with the expected enterprise
        catalog and enterprise customer associations *with restricted runs in
        the picture, and no unrestricted runs at all*.

        This DAG represents the complete test environment:

           ┌────────────────────────────────────┐
           │ courserun_restricted_for_catalog_A │
           └┬───────────────────────────────────┘
            | ┌────────────────────────────────────┐
            | │ courserun_restricted_for_catalog_B │
            | └┬───────────────────────────────────┘
            |  |
        ┌───▽──▽─────────────────────────┐
        │ self.course_metadata_published │
        └────────────────────────────────┘
        """
        self.maxDiff = None
        algolia_data = self._set_up_factory_data_for_algolia()

        catalog_A = EnterpriseCatalogFactory()
        catalog_B = EnterpriseCatalogFactory()

        self.course_metadata_published.catalog_queries.set([
            # This is the important thing for this test.  The default catalog
            # query is associated with the course under test, but in algolia it
            # should NOT be associated with the course because there are no
            # unrestricted runs available for it.
            self.enterprise_catalog_query,
            # These, however, should still appear in algolia as associated.
            catalog_A.catalog_query,
            catalog_B.catalog_query,
        ])

        # Drop the standard course run since this test has no unrestricted runs at all.
        self.course_run_metadata_published.delete()
        # Drop all runs from the standard course ContentMetadata object.
        # This is another important aspect of this test---normally courses are
        # NOT indexed if they lack an advertised course run. This course WILL
        # be indexed anyway because its canonical restricted course variant
        # does have an advertised course run.
        self.course_metadata_published._json_metadata['course_runs'] = []
        self.course_metadata_published._json_metadata['advertised_course_run_uuid'] = None
        self.course_metadata_published.save()

        # Create the ContentMetadata objects for each restricted run.
        courserun_restricted_for_catalog_A = ContentMetadataFactory(
            content_type=COURSE_RUN,
            content_key='courserun_restricted_for_catalog_A',
            parent_content_key=self.course_metadata_published.content_key,
        )
        courserun_restricted_for_catalog_B = ContentMetadataFactory(
            content_type=COURSE_RUN,
            content_key='courserun_restricted_for_catalog_B',
            parent_content_key=self.course_metadata_published.content_key,
        )

        # Update the content filters of each catalog query to explicitly allow
        # their respective restricted runs.
        catalog_A.catalog_query.content_filter.update({
            'restricted_runs_allowed': {
                f'course:{self.course_metadata_published.content_key}': [
                    courserun_restricted_for_catalog_A.content_key,
                ]
            }
        })
        catalog_A.catalog_query.save()
        catalog_B.catalog_query.content_filter.update({
            'restricted_runs_allowed': {
                f'course:{self.course_metadata_published.content_key}': [
                    courserun_restricted_for_catalog_B.content_key,
                ]
            }
        })
        catalog_B.catalog_query.save()

        # Create the RestrictedCourseMetadata objects, respresenting different
        # views of the same course from the perspective of different catalog
        # queries.
        restricted_course_for_catalog_A = RestrictedCourseMetadataFactory(
            content_type=COURSE,
            content_key=self.course_metadata_published.content_key,
            unrestricted_parent=self.course_metadata_published,
            catalog_query=catalog_A.catalog_query,
            _json_metadata=self.course_metadata_published._json_metadata | {
                'advertised_course_run_uuid': courserun_restricted_for_catalog_A.content_uuid,
                'foobar': 'override metadata from restricted_course_for_catalog_A',
            },
        )
        restricted_course_for_catalog_A._json_metadata['course_runs'] = [
            courserun_restricted_for_catalog_A._json_metadata
        ]
        restricted_course_for_catalog_A.save()
        restricted_course_for_catalog_B = RestrictedCourseMetadataFactory(
            content_type=COURSE,
            content_key=self.course_metadata_published.content_key,
            unrestricted_parent=self.course_metadata_published,
            catalog_query=catalog_B.catalog_query,
            _json_metadata=self.course_metadata_published._json_metadata | {
                'advertised_course_run_uuid': courserun_restricted_for_catalog_B.content_uuid,
                'foobar': 'override metadata from restricted_course_for_catalog_B',
            },
        )
        restricted_course_for_catalog_B._json_metadata['course_runs'] = [
            courserun_restricted_for_catalog_B._json_metadata,
        ]
        restricted_course_for_catalog_B.save()
        restricted_course_canonical = RestrictedCourseMetadataFactory(
            content_type=COURSE,
            content_key=self.course_metadata_published.content_key,
            unrestricted_parent=self.course_metadata_published,
            catalog_query=None,
            _json_metadata=self.course_metadata_published._json_metadata | {
                'advertised_course_run_uuid': courserun_restricted_for_catalog_B.content_uuid,
                'foobar': 'override metadata from restricted_course_canonical',
            },
        )

        # Create the "canonical" restricted course.  This is a convenience
        # record for simplifying algolia indexing.
        restricted_course_canonical._json_metadata['course_runs'] = [
            courserun_restricted_for_catalog_A._json_metadata,
            courserun_restricted_for_catalog_B._json_metadata,
        ]
        restricted_course_canonical.save()

        # Finally, connect all the restricted runs to their correct
        # RestrictedCourseMetadata objects. This association is only read by
        # the algolia indexing logic to determine the catalog queries
        # associated with a unicorn course.
        RestrictedRunAllowedForRestrictedCourseFactory(
            course=restricted_course_for_catalog_A,
            run=courserun_restricted_for_catalog_A,
        )
        RestrictedRunAllowedForRestrictedCourseFactory(
            course=restricted_course_for_catalog_B,
            run=courserun_restricted_for_catalog_B,
        )

        actual_algolia_products_sent = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent
            actual_algolia_products_sent = list(products_iterable)
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS + ['foobar']):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        products_found_log_records = [record for record in info_logs.output if ' products found.' in record]
        assert ' 6 products found.' in products_found_log_records[0]

        # create expected data to be added/updated in the Algolia index.
        expected_algolia_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': sorted([
                str(catalog_A.uuid),
                str(catalog_B.uuid),
            ]),
            'academy_uuids': [],
            'academy_tags': [],
            'foobar': 'override metadata from restricted_course_canonical',
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': sorted([
                str(catalog_A.enterprise_uuid),
                str(catalog_B.enterprise_uuid),
            ]),
            'academy_uuids': [],
            'academy_tags': [],
            'foobar': 'override metadata from restricted_course_canonical',
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted([
                str(catalog_A.catalog_query.uuid),
                str(catalog_B.catalog_query.uuid),
            ]),
            'enterprise_catalog_query_titles': sorted([
                catalog_A.catalog_query.title,
                catalog_B.catalog_query.title,
            ]),
            'academy_uuids': [],
            'academy_tags': [],
            'foobar': 'override metadata from restricted_course_canonical',
        })

        # Verify replace_all_objects is called with the correct Algolia object data.
        # Create Spanish versions of expected objects
        expected_spanish_objects = [
            self._create_expected_spanish_object(obj) for obj in expected_algolia_objects_to_index
        ]
        expected_all_objects = expected_algolia_objects_to_index + expected_spanish_objects
        
        expected_call_args = sorted(expected_all_objects, key=itemgetter('objectID'))
        actual_call_args = sorted(actual_algolia_products_sent, key=itemgetter('objectID'))
        assert expected_call_args == self._sort_tags_in_algolia_object_list(actual_call_args)

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    def test_index_algolia_with_batched_uuids(self, mock_search_client):
        """
        Assert that the correct data is sent to Algolia index, with the expected enterprise
        catalog, enterprise customer, and catalog query associations.
        """
        algolia_data = self._set_up_factory_data_for_algolia()

        actual_algolia_products_sent = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent
            actual_algolia_products_sent = list(products_iterable)
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_UUID_BATCH_SIZE', 1), \
                mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        assert ' 12 products found.' in info_logs.output[-1]

        # create expected data to be added/updated in the Algolia index.
        expected_algolia_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': [algolia_data['catalog_uuids'][0]],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-1',
            'enterprise_catalog_uuids': [algolia_data['catalog_uuids'][1]],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': [algolia_data['customer_uuids'][0]],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-1',
            'enterprise_customer_uuids': [algolia_data['customer_uuids'][1]],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': [algolia_data['query_uuids'][0]],
            'enterprise_catalog_query_titles': [algolia_data['query_titles'][0]],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-1',
            'enterprise_catalog_query_uuids': [algolia_data['query_uuids'][1]],
            'enterprise_catalog_query_titles': [],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        # verify replace_all_objects is called with the correct Algolia object data
        # Create Spanish versions of expected objects
        expected_spanish_objects = [
            self._create_expected_spanish_object(obj) for obj in expected_algolia_objects_to_index
        ]
        expected_all_objects = expected_algolia_objects_to_index + expected_spanish_objects
        
        actual_all_products = sorted(actual_algolia_products_sent, key=itemgetter('objectID'))
        expected_all_sorted = sorted(expected_all_objects, key=itemgetter('objectID'))
        self.assertEqual(expected_all_sorted, actual_all_products)
        mock_search_client().replace_all_objects.assert_called_once()

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    def test_index_algolia_with_important_catalog_titles(self, mock_search_client):
        """
        Assert that every Algolia batch contains all the explore UI catalog titles
        """
        algolia_data = self._set_up_factory_data_for_algolia()
        # override the explore UI titles with test data to show every batch contains them
        explore_titles = [algolia_data['query_titles'][0]]

        actual_algolia_products_sent = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent
            actual_algolia_products_sent = list(products_iterable)
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_UUID_BATCH_SIZE', 1), \
                mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS), \
                mock.patch('enterprise_catalog.apps.api.tasks.EXPLORE_CATALOG_TITLES', explore_titles):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        assert ' 12 products found.' in info_logs.output[-1]

        # create expected data to be added/updated in the Algolia index.
        expected_algolia_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': [algolia_data['catalog_uuids'][0]],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-1',
            'enterprise_catalog_uuids': [algolia_data['catalog_uuids'][1]],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': [algolia_data['customer_uuids'][0]],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-1',
            'enterprise_customer_uuids': [algolia_data['customer_uuids'][1]],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': [algolia_data['query_uuids'][0]],
            'enterprise_catalog_query_titles': [algolia_data['query_titles'][0]],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })

        # the title is also in the second batch
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-1',
            'enterprise_catalog_query_uuids': [algolia_data['query_uuids'][1]],
            'enterprise_catalog_query_titles': [algolia_data['query_titles'][0]],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })

        # verify replace_all_objects is called with the correct Algolia object data
        # Create Spanish versions of expected objects
        expected_spanish_objects = [
            self._create_expected_spanish_object(obj) for obj in expected_algolia_objects_to_index
        ]
        expected_all_objects = expected_algolia_objects_to_index + expected_spanish_objects
        
        actual_all_products = sorted(actual_algolia_products_sent, key=itemgetter('objectID'))
        expected_all_sorted = sorted(expected_all_objects, key=itemgetter('objectID'))
        self.assertEqual(expected_all_sorted, actual_all_products)
        mock_search_client().replace_all_objects.assert_called_once()

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    def test_index_algolia_duplicate_content_uuids(self, mock_search_client):
        """
        When multiple ContentMetadata objects have identical content_uuid values, they result in algolia objectID
        collisions.  In this case we should check that the output logging indicates the correct records were discarded.
        """
        # Create a course that has a unique content_key but overlapping content_uuid with an existing course.
        ContentMetadataFactory(
            content_type=COURSE,
            content_key='duplicateX',
            content_uuid=self.course_metadata_published.content_uuid
        )
        course_run_for_duplicate = ContentMetadataFactory(content_type=COURSE_RUN, parent_content_key='duplicateX')
        course_run_for_duplicate.catalog_queries.set([self.enterprise_catalog_course_runs.catalog_query])
        _hydrate_course_normalized_metadata()

        actual_algolia_products_sent_sequence = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent_sequence` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent_sequence
            actual_algolia_products_sent_sequence.append(list(products_iterable))
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS), \
                mock.patch('enterprise_catalog.apps.api.tasks.REINDEX_TASK_BATCH_SIZE', 1):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        histogram_found_log_records = [record for record in info_logs.output if ' Histogram of ' in record]
        assert (
            f"[ENTERPRISE_CATALOG_ALGOLIA_REINDEX] Histogram of top 10 most frequently discarded algolia object IDs: ["
            f"('course-{self.course_metadata_published.content_uuid}-catalog-uuids-0', 1), "
            f"('course-{self.course_metadata_published.content_uuid}-customer-uuids-0', 1), "
            f"('course-{self.course_metadata_published.content_uuid}-catalog-query-uuids-0', 1)"
        ) in histogram_found_log_records[0]

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    def test_index_algolia_dry_run(self, mock_search_client):
        """
        Make sure the dry_run argument functions correctly and does not call replace_all_objects().
        """
        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_UUID_BATCH_SIZE', 1), \
                mock.patch('enterprise_catalog.apps.api.tasks.REINDEX_TASK_BATCH_SIZE', 10), \
                mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS):
            with self.assertLogs(level='INFO') as info_logs:
                # For some reason in order to call a celery task in-memory you must pass kwargs as args.
                force = False
                dry_run = True
                tasks.index_enterprise_catalog_in_algolia_task(force, dry_run)

        mock_search_client().replace_all_objects.assert_not_called()
        assert '[ENTERPRISE_CATALOG_ALGOLIA_REINDEX] [DRY RUN] 12 products found.' in info_logs.output[-1]
        assert any(
            '[ENTERPRISE_CATALOG_ALGOLIA_REINDEX] [DRY RUN] skipping algolia_client.replace_all_objects().' in record
            for record in info_logs.output
        )

    @mock.patch('enterprise_catalog.apps.api.tasks._fetch_courses_by_keys')
    @mock.patch('enterprise_catalog.apps.api.tasks.DiscoveryApiClient.get_course_reviews')
    @mock.patch('enterprise_catalog.apps.api.tasks.ContentMetadata.objects.filter')
    @mock.patch('enterprise_catalog.apps.api.tasks.create_course_associated_programs')
    @mock.patch('enterprise_catalog.apps.api.tasks._update_full_content_metadata_program')
    def test_update_full_content_metadata_course(
        self,
        mock_update_content_metadata_program,
        mock_create_course_associated_programs,
        mock_filter,
        mock_get_course_reviews,
        mock_fetch_courses_by_keys
    ):
        # Mock data
        content_keys = ['course1', 'course2']
        full_course_dicts = [
            {'key': 'course1', 'title': 'Course 1', FORCE_INCLUSION_METADATA_TAG_KEY: True},
            {'key': 'course2', 'title': 'Course 2'}
        ]
        reviews_for_courses_dict = {
            'course1': {'reviews_count': 10, 'avg_course_rating': 4.5},
            'course2': {'reviews_count': 5, 'avg_course_rating': 3.8}
        }
        content_metadata_1 = ContentMetadataFactory(content_type=COURSE, content_key='course1')
        content_metadata_2 = ContentMetadataFactory(content_type=COURSE, content_key='course2')
        metadata_records_for_fetched_keys = [content_metadata_1, content_metadata_2]

        # Configure mock objects
        mock_fetch_courses_by_keys.return_value = full_course_dicts
        mock_get_course_reviews.return_value = reviews_for_courses_dict
        mock_filter.return_value = metadata_records_for_fetched_keys

        # Call the function
        tasks._update_full_content_metadata_course(content_keys)  # pylint: disable=protected-access

        mock_fetch_courses_by_keys.assert_called_once_with(content_keys)
        mock_get_course_reviews.assert_called_once_with(['course1', 'course2'])
        mock_filter.assert_called_once_with(content_key__in=['course1', 'course2'])

        content_metadata_1.refresh_from_db()
        content_metadata_2.refresh_from_db()
        assert content_metadata_1.json_metadata.get('reviews_count') == 10
        assert content_metadata_1.json_metadata.get('avg_course_rating') == 4.5
        assert content_metadata_2.json_metadata.get('reviews_count') == 5
        assert content_metadata_2.json_metadata.get('avg_course_rating') == 3.8

        self.assertEqual(mock_update_content_metadata_program.call_count, 2)
        self.assertEqual(mock_create_course_associated_programs.call_count, 2)

    @mock.patch('enterprise_catalog.apps.api.tasks._fetch_courses_by_keys')
    @mock.patch('enterprise_catalog.apps.api.tasks.DiscoveryApiClient.get_course_reviews')
    @mock.patch('enterprise_catalog.apps.api.tasks.ContentMetadata.objects.filter')
    @mock.patch('enterprise_catalog.apps.api.tasks.create_course_associated_programs')
    @mock.patch('enterprise_catalog.apps.api.tasks._update_full_content_metadata_program')
    @override_settings(SHOULD_FETCH_RESTRICTED_COURSE_RUNS=True)
    def test_update_full_content_metadata_course_with_restricted_runs(
        self,
        mock_update_content_metadata_program,
        mock_create_course_associated_programs,
        mock_filter,
        mock_get_course_reviews,
        mock_fetch_courses_by_keys
    ):
        # Mock data
        course_1_uuid = uuid.uuid4()
        course_run_1_uuid = uuid.uuid4()
        restricted_run_1_uuid = uuid.uuid4()
        restricted_run_2_uuid = uuid.uuid4()
        content_keys = ['course1', 'course2']
        reviews_for_courses_dict = {
            'course1': {'reviews_count': 10, 'avg_course_rating': 4.5},
            'course2': {'reviews_count': 5, 'avg_course_rating': 3.8}
        }
        content_metadata_1 = ContentMetadataFactory(content_type=COURSE, content_key='course1')
        content_metadata_2 = ContentMetadataFactory(content_type=COURSE, content_key='course2')
        content_metadata_run_1 = ContentMetadataFactory(  # pylint: disable=unused-variable
            content_type=COURSE_RUN,
            content_key='course-run-1',
        )
        content_metadata_restricted_run_1 = ContentMetadataFactory(
            content_type=COURSE_RUN,
            content_key='course-run-1-restricted'
        )
        content_metadata_restricted_run_2 = ContentMetadataFactory(  # pylint: disable=unused-variable
            content_type=COURSE_RUN,
            content_key='course-run-2-restricted'
        )
        metadata_records_for_fetched_keys = [content_metadata_1, content_metadata_2]

        catalog_query = CatalogQueryFactory(
            content_filter={
                'restricted_runs_allowed': {
                    'course:course1': [
                        'course-run-1-restricted',
                    ],
                },
            },
        )
        restricted_course = RestrictedCourseMetadataFactory(
            unrestricted_parent=content_metadata_1,
            catalog_query=catalog_query,
            content_type=COURSE,
            content_key='course1',
            _json_metadata={
                'course_runs': [
                    {
                        'key': 'course-run-1',
                        'uuid': course_run_1_uuid,
                        'aggregation_key': 'courserun:course1',
                    },
                    {
                        'key': 'course-run-1-restricted',
                        'uuid': restricted_run_1_uuid,
                        'aggregation_key': 'courserun:course1',
                        COURSE_RUN_RESTRICTION_TYPE_KEY: 'anything',
                    },
                ]
            }
        )
        RestrictedRunAllowedForRestrictedCourseFactory(
            course=restricted_course,
            run=content_metadata_restricted_run_1,
        )
        canonical_restricted_course = RestrictedCourseMetadataFactory(
            unrestricted_parent=content_metadata_1,
            catalog_query=None,
            content_type=COURSE,
            content_key='course1',
            _json_metadata={
                'course_runs': [
                    {
                        'key': 'course-run-1',
                        'uuid': course_run_1_uuid,
                        'aggregation_key': 'courserun:course1',
                    },
                    {
                        'key': 'course-run-1-restricted',
                        'aggregation_key': 'courserun:course1',
                        'uuid': restricted_run_1_uuid,
                        COURSE_RUN_RESTRICTION_TYPE_KEY: 'anything',
                    },
                    {
                        'key': 'course-run-2-restricted',
                        'uuid': restricted_run_2_uuid,
                        'aggregation_key': 'courserun:course1',
                        COURSE_RUN_RESTRICTION_TYPE_KEY: 'anything',
                    },
                ],
            }
        )

        # Configure mock objects
        mock_fetch_courses_by_keys.side_effect = [
            # First call to /api/v1/courses originates from the top of
            # _update_full_content_metadata_course(), so it does NOT pass the
            # `?include_restricted=` query parameter.  Therefore, no restricted
            # runs should be included in the mock response.
            [
                {
                    'key': 'course1',
                    'uuid': course_1_uuid,
                    'aggregation_key': 'course:course1',
                    'title': 'Course 1',
                    FORCE_INCLUSION_METADATA_TAG_KEY: True,
                    'course_runs': [
                        {
                            'key': 'course-run-1',
                            'uuid': course_1_uuid,
                            'aggregation_key': 'courserun:course1',
                        },
                    ]
                },
                {
                    'key': 'course2',
                    'title': 'Course 2',
                },
            ],
            # Second call to /api/v1/courses originates from
            # _update_full_restricted_course_metadata(), so it passess the
            # `?include_restricted=` query parameter to include all the
            # restricted runs for the course.
            [
                {
                    'key': 'course1',
                    'uuid': course_1_uuid,
                    'title': 'Course 1',
                    FORCE_INCLUSION_METADATA_TAG_KEY: True,
                    'course_runs': [
                        {
                            'key': 'course-run-1',
                            'uuid': course_run_1_uuid,
                            'aggregation_key': 'courserun:course1'
                        },
                        {
                            'key': 'course-run-1-restricted',
                            'uuid': restricted_run_1_uuid,
                            'aggregation_key': 'courserun:course1',
                            COURSE_RUN_RESTRICTION_TYPE_KEY: 'anything',
                        },
                        {
                            'key': 'course-run-2-restricted',
                            'uuid': restricted_run_2_uuid,
                            'aggregation_key': 'courserun:course1',
                            COURSE_RUN_RESTRICTION_TYPE_KEY: 'anything',
                        },
                    ],
                    # Throw in this extra key to the mock response, so that
                    # later we can validate that it gets merged into the final
                    # metadata for the restricted course.
                    'other': 'stuff',
                },
            ]
        ]
        mock_get_course_reviews.return_value = reviews_for_courses_dict
        mock_filter.return_value = metadata_records_for_fetched_keys

        # Call the function
        tasks._update_full_content_metadata_course(content_keys)  # pylint: disable=protected-access

        mock_fetch_courses_by_keys.assert_has_calls([
            mock.call(content_keys),
            mock.call([restricted_course.content_key], extra_query_params=QUERY_FOR_RESTRICTED_RUNS),
        ])
        mock_get_course_reviews.assert_called_once_with(['course1', 'course2'])
        mock_filter.assert_called_once_with(content_key__in=['course1', 'course2'])

        content_metadata_1.refresh_from_db()
        content_metadata_2.refresh_from_db()
        assert content_metadata_1.json_metadata.get('reviews_count') == 10
        assert content_metadata_1.json_metadata.get('avg_course_rating') == 4.5
        assert content_metadata_2.json_metadata.get('reviews_count') == 5
        assert content_metadata_2.json_metadata.get('avg_course_rating') == 3.8

        self.assertEqual(mock_update_content_metadata_program.call_count, 2)
        self.assertEqual(mock_create_course_associated_programs.call_count, 2)

        # Test that the extra keys from the /api/v1/courses response were
        # appropriately merged into the restricted course metadata, and the
        # restricted runs were preserved.
        restricted_course.refresh_from_db()
        self.assertEqual('stuff', restricted_course.json_metadata['other'])
        self.assertEqual(
            {run['key'] for run in restricted_course.json_metadata['course_runs']},
            {'course-run-1', 'course-run-1-restricted'},
        )
        # The canonical restricted course record should STILL contain two
        # restricted runs and a non-restricted run, as well as the extra key.
        canonical_restricted_course.refresh_from_db()
        self.assertEqual('stuff', canonical_restricted_course.json_metadata['other'])
        self.assertEqual(
            {run['key'] for run in canonical_restricted_course.json_metadata['course_runs']},
            {'course-run-1', 'course-run-1-restricted', 'course-run-2-restricted'},
        )

    @mock.patch('enterprise_catalog.apps.api.tasks._fetch_courses_by_keys')
    @mock.patch('enterprise_catalog.apps.api.tasks.DiscoveryApiClient.get_course_reviews')
    @mock.patch('enterprise_catalog.apps.api.tasks.ContentMetadata.objects.filter')
    @mock.patch('enterprise_catalog.apps.api.tasks.create_course_associated_programs')
    @mock.patch('enterprise_catalog.apps.api.tasks._update_full_content_metadata_program')
    def test_update_full_content_metadata_course_dry_run(
        self,
        mock_update_content_metadata_program,
        mock_create_course_associated_programs,
        mock_filter,
        mock_get_course_reviews,
        mock_fetch_courses_by_keys
    ):
        # Mock data
        content_keys = ['course1', 'course2']
        full_course_dicts = [
            {'key': 'course1', 'title': 'Course 1'},
            {'key': 'course2', 'title': 'Course 2'}
        ]
        reviews_for_courses_dict = {
            'course1': {'reviews_count': 10, 'avg_course_rating': 4.5},
            'course2': {'reviews_count': 5, 'avg_course_rating': 3.8}
        }
        content_metadata_1 = ContentMetadataFactory(content_type=COURSE, content_key='course1')
        content_metadata_2 = ContentMetadataFactory(content_type=COURSE, content_key='course2')
        metadata_records_for_fetched_keys = [content_metadata_1, content_metadata_2]

        # Configure mock objects
        mock_fetch_courses_by_keys.return_value = full_course_dicts
        mock_get_course_reviews.return_value = reviews_for_courses_dict
        mock_filter.return_value = metadata_records_for_fetched_keys

        # Call the function
        tasks._update_full_content_metadata_course(content_keys, dry_run=True)  # pylint: disable=protected-access

        mock_fetch_courses_by_keys.assert_called_once_with(content_keys)
        mock_get_course_reviews.assert_called_once_with(['course1', 'course2'])
        mock_filter.assert_called_once_with(content_key__in=['course1', 'course2'])

        content_metadata_1.refresh_from_db()
        content_metadata_2.refresh_from_db()
        assert content_metadata_1.json_metadata.get('reviews_count') is None
        assert content_metadata_1.json_metadata.get('avg_course_rating') is None
        assert content_metadata_2.json_metadata.get('reviews_count') is None
        assert content_metadata_2.json_metadata.get('avg_course_rating') is None

        self.assertEqual(mock_update_content_metadata_program.call_count, 2)
        self.assertEqual(mock_create_course_associated_programs.call_count, 2)

    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client', return_value=mock.MagicMock())
    @override_settings(SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS=True)
    # pylint: disable=too-many-statements
    def test_index_algolia_all_uuids(self, mock_search_client):
        """
        Assert that the correct data is sent to Algolia index, with the expected enterprise
        catalog and enterprise customer associations.

        This DAG represents the complete test environment:

        ┌─────────┐┌────────────────────┐┌─────────────────────┐
        │program-2││*courserun_published││courserun_unpublished│
        └┬────────┘└┬──┬────────────────┘└┬────────────────────┘
        ┌▽──────────▽┐┌▽────────────────┐┌▽─────────────────┐
        │*pathway-2  ││*course_published││course_unpublished│
        └────────────┘└┬──┬──────────┬──┘└┬───────┬─────────┘
              ┌────────▽┐┌▽─────────┐│┌───▽──────┐│
              │program-1││*pathway-1│││*program-3││
              └─────────┘└──────────┘│└┬─────────┘│
                                    ┌▽─▽──────────▽┐
                                    │ *pathway-3   │
                                    └──────────────┘
        * = indexable
        """
        self.maxDiff = None
        algolia_data = self._set_up_factory_data_for_algolia()
        program_for_main_course = ContentMetadataFactory(content_type=PROGRAM, content_key='program-1')
        # Make the program hidden to make it "non-indexable", but ensure that it still gets indexed due to being related
        # to an indexable course.
        program_for_main_course._json_metadata.update({  # pylint: disable=protected-access
            'hidden': True,
        })
        program_for_main_course.save()
        program_for_pathway = ContentMetadataFactory(content_type=PROGRAM, content_key='program-2')
        program_for_pathway.catalog_queries.set([self.enterprise_catalog_query])
        # Make the program hidden to make it "non-indexable", but ensure that it still gets indexed due to being related
        # to an indexable pathway.
        program_for_pathway._json_metadata.update({  # pylint: disable=protected-access
            'hidden': True,
        })
        program_for_pathway.save()
        pathway_for_course = ContentMetadataFactory(content_type=LEARNER_PATHWAY, content_key='pathway-1')
        pathway_for_courserun = ContentMetadataFactory(content_type=LEARNER_PATHWAY, content_key='pathway-2')

        # pathway-2 is indexable, but since it is not associated with any other indexable object that is in a catalog
        # query, it will not be indexed unless we add it directly to a catalog query.
        pathway_for_courserun.catalog_queries.set([self.enterprise_catalog_query])

        # Set up a program and pathway, both intended to be associated to the unpublished course to test that the course
        # does not get indexed through association.  The pathway also needs to be associated directly with the main
        # course so that it will actually have UUIDs and be included in the output.
        program_for_unpublished_course = ContentMetadataFactory(content_type=PROGRAM, content_key='program-3')
        program_for_unpublished_course.catalog_queries.set([self.enterprise_catalog_query])
        pathway_for_unpublished_course = ContentMetadataFactory(content_type=LEARNER_PATHWAY, content_key='pathway-3')

        # associate program and pathway with the course
        self.course_metadata_published.associated_content_metadata.set(
            [program_for_main_course, pathway_for_course, pathway_for_unpublished_course]
        )
        # associate pathway with the course run
        self.course_run_metadata_published.associated_content_metadata.set(
            [pathway_for_courserun]
        )
        # associate pathway with the program
        program_for_pathway.associated_content_metadata.set(
            [pathway_for_courserun]
        )
        # associate unpublished course with the program and pathway made for testing it.
        self.course_metadata_unpublished.associated_content_metadata.set(
            [program_for_unpublished_course, pathway_for_unpublished_course]
        )

        actual_algolia_products_sent = []

        # `replace_all_objects` is swapped out for a mock implementation that forces generator evaluation and saves the
        # result into `actual_algolia_products_sent` for unit testing.
        def mock_replace_all_objects(products_iterable):
            nonlocal actual_algolia_products_sent
            actual_algolia_products_sent = list(products_iterable)
        mock_search_client().replace_all_objects.side_effect = mock_replace_all_objects

        with mock.patch('enterprise_catalog.apps.api.tasks.ALGOLIA_FIELDS', self.ALGOLIA_FIELDS):
            with self.assertLogs(level='INFO') as info_logs:
                tasks.index_enterprise_catalog_in_algolia_task()  # pylint: disable=no-value-for-parameter

        products_found_log_records = [record for record in info_logs.output if ' products found.' in record]
        assert ' 30 products found.' in products_found_log_records[0]

        # create expected data to be added/updated in the Algolia index.
        expected_algolia_objects_to_index = []
        published_course_uuid = algolia_data['course_metadata_published'].json_metadata.get('uuid')
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': algolia_data['catalog_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': algolia_data['customer_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_objects_to_index.append({
            'key': algolia_data['course_metadata_published'].content_key,
            'objectID': f'course-{published_course_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted(algolia_data['query_uuids']),
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })

        expected_algolia_program_objects3 = []
        program_uuid = program_for_unpublished_course.json_metadata.get('uuid')
        expected_algolia_program_objects3.append({
            'objectID': f'program-{program_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': [str(self.enterprise_catalog_courses.uuid)],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })
        expected_algolia_program_objects3.append({
            'objectID': f'program-{program_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': [str(self.enterprise_catalog_courses.enterprise_uuid)],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })
        expected_algolia_program_objects3.append({
            'objectID': f'program-{program_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': [str(self.enterprise_catalog_courses.catalog_query.uuid)],
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })

        expected_algolia_pathway_objects = []
        pathway_uuid = pathway_for_course.json_metadata.get('uuid')
        expected_algolia_pathway_objects.append({
            'key': pathway_for_course.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': algolia_data['catalog_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_pathway_objects.append({
            'key': pathway_for_course.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': algolia_data['customer_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_pathway_objects.append({
            'key': pathway_for_course.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted(algolia_data['query_uuids']),
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })

        expected_algolia_pathway_objects2 = []
        pathway_uuid = pathway_for_courserun.json_metadata.get('uuid')
        expected_algolia_pathway_objects2.append({
            'key': pathway_for_courserun.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': [str(self.enterprise_catalog_courses.uuid)],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })
        expected_algolia_pathway_objects2.append({
            'key': pathway_for_courserun.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': [str(self.enterprise_catalog_courses.enterprise_uuid)],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })
        expected_algolia_pathway_objects2.append({
            'key': pathway_for_courserun.content_key,
            'objectID': f'learnerpathway-{pathway_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': [str(self.enterprise_catalog_courses.catalog_query.uuid)],
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': [],
        })

        expected_algolia_pathway_objects3 = []
        pathway_key = pathway_for_unpublished_course.content_key
        pathway_uuid = pathway_for_unpublished_course.json_metadata.get('uuid')
        expected_algolia_pathway_objects3.append({
            'key': pathway_key,
            'objectID': f'learnerpathway-{pathway_uuid}-catalog-uuids-0',
            'enterprise_catalog_uuids': algolia_data['catalog_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_pathway_objects3.append({
            'key': pathway_key,
            'objectID': f'learnerpathway-{pathway_uuid}-customer-uuids-0',
            'enterprise_customer_uuids': algolia_data['customer_uuids'],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })
        expected_algolia_pathway_objects3.append({
            'key': pathway_key,
            'objectID': f'learnerpathway-{pathway_uuid}-catalog-query-uuids-0',
            'enterprise_catalog_query_uuids': sorted(algolia_data['query_uuids']),
            'enterprise_catalog_query_titles': [self.enterprise_catalog_courses.catalog_query.title],
            'academy_uuids': algolia_data['academy_uuids'],
            'academy_tags': algolia_data['academy_tags'],
        })

        expected_algolia_objects_to_index = (
            expected_algolia_objects_to_index
            + expected_algolia_program_objects3
            + expected_algolia_pathway_objects
            + expected_algolia_pathway_objects2
            + expected_algolia_pathway_objects3
        )

        # verify replace_all_objects is called with the correct Algolia object data
        # on the first invocation and with programs/pathways only on the second invocation.
        # Create Spanish versions of expected objects
        expected_spanish_objects = [
            self._create_expected_spanish_object(obj) for obj in expected_algolia_objects_to_index
        ]
        expected_all_objects = expected_algolia_objects_to_index + expected_spanish_objects
        
        expected_call_args = sorted(expected_all_objects, key=itemgetter('objectID'))
        actual_call_args = sorted(actual_algolia_products_sent, key=itemgetter('objectID'))
        assert expected_call_args == self._sort_tags_in_algolia_object_list(actual_call_args)
