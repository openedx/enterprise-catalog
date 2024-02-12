from uuid import uuid4

from django.test import TestCase

from enterprise_catalog.apps.catalog.content_metadata_utils import (
    tansform_force_included_courses,
    transform_course_metadata_to_visible,
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
