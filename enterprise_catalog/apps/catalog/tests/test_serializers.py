"""
Unit tests for the ``catalog.serializers`` module.
"""
import ddt
from django.test import TestCase

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    EXEC_ED_2U_COURSE_TYPE,
)
from enterprise_catalog.apps.catalog.content_metadata_utils import (
    get_advertised_course_run,
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
            'course_metadata': course_content.json_metadata,
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
            'course_metadata': course_content.json_metadata,
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
            'course_metadata': course_content.json_metadata,
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
            'course_metadata': course_content.json_metadata,
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
            'course_metadata': course_content.json_metadata,
        }
        if has_course_run:
            normalized_metadata_input['course_run_metadata'] = course_content.json_metadata['course_runs'][0]

        serialized_data = NormalizedContentMetadataSerializer(normalized_metadata_input).data

        self.assertEqual(serialized_data['enroll_by_date'], actual_deadline)

    @ddt.data(
        # WHEN first_enrollable_paid_seat_price is available,
        # THEN use first_enrollable_paid_seat_price.
        {
            'first_enrollable_paid_seat_price': 50,
            'fixed_price_usd': None,
            'entitlements': [],
            'course_type': 'verified-audit',
            'expected_content_price': 50.0,
        },
        # WHEN neither first_enrollable_paid_seat_price nor fixed price exist,
        # THEN fall back to default price.
        {
            'first_enrollable_paid_seat_price': None,
            'fixed_price_usd': None,
            'entitlements': [],
            'course_type': 'verified-audit',
            'expected_content_price': 0.0,
        },
        # WHEN a fixed price exists, but so does a first_enrollable_paid_seat_price,
        # THEN prioritize the fixed price.
        {
            'first_enrollable_paid_seat_price': 50,
            'fixed_price_usd': "100.00",
            'entitlements': [],
            'course_type': 'verified-audit',
            'expected_content_price': 100.0,
        },
        # WHEN no fixed price and course type is Exec Ed,
        # THEN use entitlements price.
        {
            'first_enrollable_paid_seat_price': None,
            'fixed_price_usd': None,
            'entitlements': [
                {
                    "mode": "paid-executive-education",
                    "price": "200.00",
                    "currency": "USD",
                    "sku": "1234",
                    "expires": None
                }
            ],
            'course_type': 'executive-education-2u',
            'expected_content_price': 200.0,
        },
        # wHEN no fixed price, course type is Exec Ed, and the entitlements price is None,
        # THEN fall back to default price.
        {
            'first_enrollable_paid_seat_price': None,
            'fixed_price_usd': None,
            'entitlements': [
                {
                    "mode": "paid-executive-education",
                    "price": None,  # trigger fallback to default price.
                    "currency": "USD",
                    "sku": "1234",
                    "expires": None
                }
            ],
            'course_type': 'executive-education-2u',
            'expected_content_price': 0,
        },
        # wHEN no fixed price, course type is Exec Ed, no advertised course run,
        # THEN use entitlements price.
        {
            'first_enrollable_paid_seat_price': None,
            'fixed_price_usd': None,
            'entitlements': [
                {
                    "mode": "paid-executive-education",
                    "price": "200.00",
                    "currency": "USD",
                    "sku": "1234",
                    "expires": None
                }
            ],
            'course_type': 'executive-education-2u',
            'has_advertised_course_run': False,
            'expected_content_price': 200.0,
        },
        # wHEN no fixed price, course type is Exec Ed, no advertised course run, entitlements price is None,
        # THEN fall back to default price.
        {
            'first_enrollable_paid_seat_price': None,
            'fixed_price_usd': None,
            'entitlements': [
                {
                    "mode": "paid-executive-education",
                    "price": None,
                    "currency": "USD",
                    "sku": "1234",
                    "expires": None
                }
            ],
            'course_type': 'executive-education-2u',
            'has_advertised_course_run': False,
            'expected_content_price': 0,
        },
    )
    @ddt.unpack
    def test_content_price(self,
                           first_enrollable_paid_seat_price,
                           fixed_price_usd,
                           entitlements,
                           course_type,
                           expected_content_price,
                           has_advertised_course_run=True,
                           ):
        course_content = factories.ContentMetadataFactory(
            content_type=COURSE,
        )
        course_content.json_metadata['entitlements'] = entitlements
        course_content.json_metadata['course_type'] = course_type

        advertised_course_run = get_advertised_course_run(course_content.json_metadata)
        advertised_course_run['fixed_price_usd'] = fixed_price_usd
        advertised_course_run['first_enrollable_paid_seat_price'] = first_enrollable_paid_seat_price

        if not has_advertised_course_run:
            course_content.json_metadata['advertised_course_run_uuid'] = None

        normalized_metadata_input = {
            'course_metadata': course_content.json_metadata,
            'course_run_metadata': course_content.json_metadata['course_runs'][0]
        }

        serialized_data = NormalizedContentMetadataSerializer(normalized_metadata_input).data

        self.assertEqual(serialized_data['content_price'], expected_content_price)
