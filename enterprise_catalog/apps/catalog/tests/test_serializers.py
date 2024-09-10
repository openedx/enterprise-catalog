"""
Unit tests for the ``catalog.serializers`` module.
"""
import ddt
from django.test import TestCase

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    EXEC_ED_2U_COURSE_TYPE,
)
from enterprise_catalog.apps.catalog.serializers import (
    NormalizedContentMetadataSerializer,
)
from enterprise_catalog.apps.catalog.tests import factories


@ddt.ddt
class NormalizedContentMetadataSerializerTests(TestCase):
    """
    Tests for ``NormalizedContentMetadataSerializer``.
    """

    def test_enroll_by_date_no_advertised_run(self):
        course_content = factories.ContentMetadataFactory(
            content_type=COURSE,
        )
        course_content.json_metadata['advertised_course_run_uuid'] = None

        normalized_metadata_input = {
            'course': course_content,
        }
        serialized_data = NormalizedContentMetadataSerializer(normalized_metadata_input).data

        self.assertIsNone(serialized_data['enroll_by_date'])

    @ddt.data(
        {'has_course_run': False},
        {'has_course_run': True},
    )
    @ddt.unpack
    def test_enroll_by_date_is_exec_ed_course_with_enrollment_end(self, has_course_run):
        course_content = factories.ContentMetadataFactory(
            content_type=COURSE,
        )
        course_content.json_metadata['course_type'] = EXEC_ED_2U_COURSE_TYPE
        course_content.json_metadata['course_runs'] = [
            {
                'uuid': 'the-course-run-uuid',
                'enrollment_end': '2024-01-01T00:00:00Z',
            }
        ]
        course_content.json_metadata['advertised_course_run_uuid'] = 'the-course-run-uuid'

        normalized_metadata_input = {
            'course': course_content,
        }
        if has_course_run:
            normalized_metadata_input['course_run_metadata'] = course_content.json_metadata['course_runs'][0]
        serialized_data = NormalizedContentMetadataSerializer(normalized_metadata_input).data

        self.assertEqual(serialized_data['enroll_by_date'], '2024-01-01T00:00:00Z')

    @ddt.data(
        {'has_course_run': False},
        {'has_course_run': True},
    )
    @ddt.unpack
    def test_enroll_by_date_is_exec_ed_course_no_enrollment_end(self, has_course_run):
        course_content = factories.ContentMetadataFactory(
            content_type=COURSE,
        )
        course_content.json_metadata['course_type'] = EXEC_ED_2U_COURSE_TYPE
        course_content.json_metadata['course_runs'] = [
            {
                'uuid': 'the-course-run-uuid',
                'enrollment_end': None
            }
        ]
        course_content.json_metadata['advertised_course_run_uuid'] = 'the-course-run-uuid'
        normalized_metadata_input = {
            'course': course_content,
        }
        if has_course_run:
            normalized_metadata_input['course_run_metadata'] = course_content.json_metadata['course_runs'][0]
        serialized_data = NormalizedContentMetadataSerializer(normalized_metadata_input).data

        self.assertEqual(serialized_data['enroll_by_date'], None)

    @ddt.data(
        {'has_override': True, 'has_course_run': False},
        {'has_override': False, 'has_course_run': False},
        {'has_override': True, 'has_course_run': True},
        {'has_override': False, 'has_course_run': True},
    )
    @ddt.unpack
    def test_enroll_by_date_verified_course_with_seat(self, has_override, has_course_run):
        course_content = factories.ContentMetadataFactory(
            content_type=COURSE,
        )
        actual_deadline = '2023-12-31T00:00:00Z'
        actual_deadline_override = '2024-12-31T00:00:00Z'
        course_content.json_metadata['course_runs'][0]['seats'] = [
            {
                'type': 'verified',
                'price': '50.00',
                'currency': 'USD',
                'upgrade_deadline': actual_deadline,
                'upgrade_deadline_override': actual_deadline_override if has_override else None,
                'credit_provider': None,
                'credit_hours': None,
                'sku': 'F46BB55',
                'bulk_sku': 'C72C608'
            }
        ]

        normalized_metadata_input = {
            'course': course_content,
        }
        if has_course_run:
            normalized_metadata_input['course_run_metadata'] = course_content.json_metadata['course_runs'][0]
        serialized_data = NormalizedContentMetadataSerializer(normalized_metadata_input).data

        if has_override:
            self.assertEqual(serialized_data['enroll_by_date'], actual_deadline_override)
        else:
            self.assertEqual(serialized_data['enroll_by_date'], actual_deadline)

    @ddt.data(
        {'has_course_run': False},
        {'has_course_run': True},
    )
    @ddt.unpack
    def test_enroll_by_date_verified_course_no_seat(self, has_course_run):
        course_content = factories.ContentMetadataFactory(
            content_type=COURSE,
        )
        actual_deadline = '2023-12-31T00:00:00Z'
        course_content.json_metadata['course_runs'][0]['seats'] = []
        course_content.json_metadata['course_runs'][0]['enrollment_end'] = actual_deadline

        normalized_metadata_input = {
            'course': course_content,
        }
        if has_course_run:
            normalized_metadata_input['course_run_metadata'] = course_content.json_metadata['course_runs'][0]
        serialized_data = NormalizedContentMetadataSerializer(normalized_metadata_input).data

        self.assertEqual(serialized_data['enroll_by_date'], actual_deadline)
