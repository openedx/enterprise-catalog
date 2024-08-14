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

        serialized_data = NormalizedContentMetadataSerializer(course_content).data

        self.assertIsNone(serialized_data['enroll_by_date'])

    def test_enroll_by_date_is_exec_ed_course_with_enrollment_end(self):
        course_content = factories.ContentMetadataFactory(
            content_type=COURSE,
        )
        course_content.json_metadata['course_type'] = EXEC_ED_2U_COURSE_TYPE
        course_content.json_metadata['additional_metadata'] = {
            'will': 'be ignored',
            'registration_deadline': '1999-12-31T23:59:59Z',
        }
        course_content.json_metadata['course_runs'] = [
            {
                'uuid': 'the-course-run-uuid',
                'enrollment_end': '2024-01-01T00:00:00Z',
            }
        ]
        course_content.json_metadata['advertised_course_run_uuid'] = 'the-course-run-uuid'

        serialized_data = NormalizedContentMetadataSerializer(course_content).data

        self.assertEqual(serialized_data['enroll_by_date'], '2024-01-01T00:00:00Z')

    def test_enroll_by_date_is_exec_ed_course_no_enrollment_end(self):
        course_content = factories.ContentMetadataFactory(
            content_type=COURSE,
        )
        course_content.json_metadata['course_type'] = EXEC_ED_2U_COURSE_TYPE
        course_content.json_metadata['additional_metadata'] = {
            'will': 'not be ignored',
            'registration_deadline': '1999-12-31T23:59:59Z',
        }
        course_content.json_metadata['course_runs'] = [
            {
                'uuid': 'the-course-run-uuid',
                'enrollment_end': None
            }
        ]
        course_content.json_metadata['advertised_course_run_uuid'] = 'the-course-run-uuid'

        serialized_data = NormalizedContentMetadataSerializer(course_content).data

        self.assertEqual(serialized_data['enroll_by_date'], '1999-12-31T23:59:59Z')

    @ddt.data(True, False)
    def test_enroll_by_date_verified_course_with_seat(self, has_override):
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

        serialized_data = NormalizedContentMetadataSerializer(course_content).data

        if has_override:
            self.assertEqual(serialized_data['enroll_by_date'], actual_deadline_override)
        else:
            self.assertEqual(serialized_data['enroll_by_date'], actual_deadline)

    def test_enroll_by_date_verified_course_no_seat(self):
        course_content = factories.ContentMetadataFactory(
            content_type=COURSE,
        )
        actual_deadline = '2023-12-31T00:00:00Z'
        course_content.json_metadata['course_runs'][0]['seats'] = []
        course_content.json_metadata['course_runs'][0]['enrollment_end'] = actual_deadline

        serialized_data = NormalizedContentMetadataSerializer(course_content).data

        self.assertEqual(serialized_data['enroll_by_date'], actual_deadline)
