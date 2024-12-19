from uuid import uuid4

import ddt
from django.test import TestCase

from enterprise_catalog.apps.catalog.content_metadata_utils import (
    get_advertised_course_run,
    tansform_force_included_courses,
    transform_course_metadata_to_visible,
)


ADVERTISED_COURSE_RUN_UUID = uuid4()


@ddt.ddt
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

    def test_tansform_force_included_courses(self):
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
        tansform_force_included_courses(courses)
        assert courses[0]['course_runs'][0]['status'] == 'published'

    @ddt.data(
        # Happy path: Multiple runs including advertised_course_run in course_runs, available advertised_course_run_uuid
        (
            {
                'course_runs': [
                    {
                        'key': 'course-v1:org+course+1T2021',
                        'uuid': ADVERTISED_COURSE_RUN_UUID,
                        'pacing_type': 'instructor_paced',
                        'start': '2013-10-16T14:00:00Z',
                        'end': '2014-10-16T14:00:00Z',
                        'enrollment_end': '2013-10-17T14:00:00Z',
                        'availability': 'Current',
                        'min_effort': 10,
                        'max_effort': 14,
                        'weeks_to_complete': 13,
                        'status': 'published',
                        'is_enrollable': True,
                        'is_marketable': True,
                        'enrollment_start': '2013-10-01T14:00:00Z',
                    },
                    {
                        'key': 'course-v1:org+course+1T2021',
                        'uuid': uuid4(),
                        'pacing_type': 'instructor_paced',
                        'start': '2016-10-16T14:00:00Z',
                        'end': '2019-10-16T14:00:00Z',
                        'enrollment_end': '2016-10-17T14:00:00Z',
                        'availability': 'Upcoming',
                        'min_effort': 11,
                        'max_effort': 15,
                        'weeks_to_complete': 15,
                        'status': 'published',
                        'is_enrollable': True,
                        'is_marketable': True,
                        'enrollment_start': '2013-10-01T14:00:00Z',
                    }
                ],
                'advertised_course_run_uuid': ADVERTISED_COURSE_RUN_UUID
            },
            {
                'key': 'course-v1:org+course+1T2021',
                'uuid': ADVERTISED_COURSE_RUN_UUID,
                'pacing_type': 'instructor_paced',
                'start': '2013-10-16T14:00:00Z',
                'end': '2014-10-16T14:00:00Z',
                'enrollment_end': '2013-10-17T14:00:00Z',
                'availability': 'Current',
                'min_effort': 10,
                'max_effort': 14,
                'weeks_to_complete': 13,
                'status': 'published',
                'is_enrollable': True,
                'is_marketable': True,
                'enrollment_start': '2013-10-01T14:00:00Z',
            },
        ),
        # Edge case: course_runs does not include advertised_course_run with available advertised_course_run_uuid
        (
            {
                'course_runs': [{
                    'uuid': uuid4(),
                }],
                'advertised_course_run_uuid': ADVERTISED_COURSE_RUN_UUID
            },
            None,
        ),
        # Edge case: No available course_runs and no advertised_course_run_uuid
        (
            {
                'course_runs': [],
                'advertised_course_run_uuid': None
            },
            None
        ),
        # Edge case: Available advertised_course_run within course_runs, and no advertised_course_run_uuid
        (
            {
                'course_runs': [
                    {
                        'key': 'course-v1:org+course+1T2021',
                        'uuid': ADVERTISED_COURSE_RUN_UUID,
                        'pacing_type': 'instructor_paced',
                        'start': '2013-10-16T14:00:00Z',
                        'end': '2014-10-16T14:00:00Z',
                        'enrollment_end': '2013-10-17T14:00:00Z',
                        'availability': 'Current',
                        'min_effort': 10,
                        'max_effort': 14,
                        'weeks_to_complete': 13,
                        'status': 'published',
                        'is_enrollable': True,
                        'is_marketable': True,
                        'enrollment_start': '2013-10-01T14:00:00Z',
                    },
                    {
                        'key': 'course-v1:org+course+1T2021',
                        'uuid': uuid4(),
                        'pacing_type': 'instructor_paced',
                        'start': '2016-10-16T14:00:00Z',
                        'end': '2019-10-16T14:00:00Z',
                        'enrollment_end': '2016-10-17T14:00:00Z',
                        'availability': 'Upcoming',
                        'min_effort': 11,
                        'max_effort': 15,
                        'weeks_to_complete': 15,
                        'status': 'published',
                        'is_enrollable': True,
                        'is_marketable': True,
                        'enrollment_start': '2013-10-01T14:00:00Z',
                    }
                ],
                'advertised_course_run_uuid': None
            },
            None
        ),
    )
    @ddt.unpack
    def test_get_advertised_course(self, searchable_course, expected_course_run):
        """
        Assert get_advertised_course_run fetches the expected_course_run
        """
        advertised_course_run = get_advertised_course_run(searchable_course)
        assert advertised_course_run == expected_course_run
