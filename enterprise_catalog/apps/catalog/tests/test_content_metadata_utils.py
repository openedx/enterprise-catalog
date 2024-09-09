from uuid import uuid4

from django.test import TestCase

from enterprise_catalog.apps.catalog.constants import (
    COURSE_RUN_RESTRICTION_TYPE_KEY,
)
from enterprise_catalog.apps.catalog.content_metadata_utils import (
    find_restricted_course_runs,
    remove_restricted_course_runs,
    transform_course_metadata_to_visible,
    transform_force_included_courses,
)


class ContentMetadataUtilsTests(TestCase):
    """
    Tests for content metadata utils.
    """

    def test_transform_course_metadata_to_visible(self):
        advertised_course_run_uuid = str(uuid4())
        content_metadata = {
            'advertised_course_run_uuid': advertised_course_run_uuid,
            'course_runs': [
                {
                    'uuid': advertised_course_run_uuid,
                    'status': 'unpublished',
                    'availability': 'Coming Soon',
                }
            ],
            'course_run_statuses': [
                'unpublished'
            ]
        }
        transform_course_metadata_to_visible(content_metadata)
        assert content_metadata['course_runs'][0]['status'] == 'published'
        assert content_metadata['course_runs'][0]['availability'] == 'Current'
        assert content_metadata['course_run_statuses'][0] == 'published'

    def test_transform_force_included_courses(self):
        advertised_course_run_uuid = str(uuid4())
        content_metadata = {
            'advertised_course_run_uuid': advertised_course_run_uuid,
            'course_runs': [
                {
                    'uuid': advertised_course_run_uuid,
                    'status': 'unpublished',
                    'availability': 'Coming Soon',
                }
            ],
            'course_run_statuses': [
                'unpublished'
            ]
        }
        courses = [content_metadata]
        transform_force_included_courses(courses)
        assert courses[0]['course_runs'][0]['status'] == 'published'

    def test_find_restricted_runs(self):
        course_metadata = {
            'course_runs': [
                {
                    'key': 'the-normal-run',
                    'uuid': uuid4(),
                    'status': 'published',
                },
                {
                    'key': 'the-restricted-run',
                    'uuid': uuid4(),
                    'status': 'published',
                    COURSE_RUN_RESTRICTION_TYPE_KEY: 'custom-b2b-enterprise',
                },
                {
                    'key': 'the-other-restricted-run',
                    'uuid': uuid4(),
                    'status': 'published',
                    COURSE_RUN_RESTRICTION_TYPE_KEY: 'another-restriction-type',
                },
                {
                    'key': 'another-normal-run',
                    'uuid': uuid4(),
                    'status': 'published',
                    COURSE_RUN_RESTRICTION_TYPE_KEY: None,
                },
            ]
        }

        actual_restricted_runs = find_restricted_course_runs(course_metadata)

        expected_restricted_runs = [
            course_metadata['course_runs'][1], course_metadata['course_runs'][2],
        ]
        self.assertEqual(actual_restricted_runs, expected_restricted_runs)

    def test_find_restricted_runs_none_exist(self):
        course_metadata = {
            'course_runs': [
                {
                    'key': 'the-normal-run',
                    'uuid': uuid4(),
                    'status': 'published',
                },
                {
                    'key': 'another-normal-run',
                    'uuid': uuid4(),
                    'status': 'published',
                    COURSE_RUN_RESTRICTION_TYPE_KEY: None,
                },
            ]
        }

        actual_restricted_runs = find_restricted_course_runs(course_metadata)

        self.assertEqual(actual_restricted_runs, [])

    def test_remove_restricted_runs(self):
        course_metadata = {
            'key': 'the-course-key',
            'advertised_course_run_uuid': 'advertised-run-uuid',
            'first_enrollable_paid_seat_price': 222,
            'course_run_statuses': ['published', 'unpublished'],
            'course_run_keys': [
                'the-normal-run',
                'the-restricted-run',
                'the-other-restricted-run',
                'another-normal-run',
            ],
            'course_runs': [
                {
                    'key': 'the-normal-run',
                    'uuid': 'advertised-run-uuid',
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                    'first_enrollable_paid_seat_price': 350,
                },
                {
                    'key': 'the-restricted-run',
                    'uuid': uuid4(),
                    'status': 'published',
                    COURSE_RUN_RESTRICTION_TYPE_KEY: 'custom-b2b-enterprise',
                    'first_enrollable_paid_seat_price': 222,
                },
                {
                    'key': 'the-other-restricted-run',
                    'uuid': uuid4(),
                    'status': 'unpublished',
                    COURSE_RUN_RESTRICTION_TYPE_KEY: 'another-restriction-type',
                },
                {
                    'key': 'another-normal-run',
                    'uuid': 'another-uuid',
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                    'first_enrollable_paid_seat_price': 0,
                    COURSE_RUN_RESTRICTION_TYPE_KEY: None,
                },
            ]
        }

        remove_restricted_course_runs(course_metadata)

        expected_transformation = {
            'key': 'the-course-key',
            'advertised_course_run_uuid': 'advertised-run-uuid',
            'first_enrollable_paid_seat_price': 350,
            'course_run_statuses': ['published'],
            'course_run_keys': [
                'the-normal-run',
                'another-normal-run',
            ],
            'course_runs': [
                {
                    'key': 'the-normal-run',
                    'uuid': 'advertised-run-uuid',
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                    'first_enrollable_paid_seat_price': 350,
                },
                {
                    'key': 'another-normal-run',
                    'uuid': 'another-uuid',
                    'status': 'published',
                    'is_enrollable': True,
                    'is_marketable': True,
                    'first_enrollable_paid_seat_price': 0,
                    COURSE_RUN_RESTRICTION_TYPE_KEY: None,
                },
            ]
        }
        self.assertEqual(expected_transformation, course_metadata)
