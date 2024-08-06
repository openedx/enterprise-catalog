"""
Defines serializers to process data at the boundaries
of the `catalog` domain.
"""
import logging

from django.utils.functional import cached_property
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from enterprise_catalog.apps.api.constants import CourseMode

from .algolia_utils import _get_course_run_by_uuid


logger = logging.getLogger(__name__)

# The default normalized content price for any content which otherwise
# would have a null price
DEFAULT_NORMALIZED_PRICE = 0.0

# The closer a mode is to the beginning of this list, the more likely a seat with that mode will be used to find the
# upgrade deadline for the course (and course run).
BEST_MODE_ORDER = [
    CourseMode.VERIFIED,
    CourseMode.PROFESSIONAL,
    CourseMode.NO_ID_PROFESSIONAL_MODE,
    CourseMode.UNPAID_EXECUTIVE_EDUCATION,
    CourseMode.AUDIT,
]


def _find_best_mode_seat(seats):
    """
    Find the seat with the "best" course mode.  See BEST_MODE_ORDER to find which modes are best.
    """
    sort_key_for_mode = {mode: index for (index, mode) in enumerate(BEST_MODE_ORDER)}

    def sort_key(seat):
        """
        Get a sort key (int) for a seat dictionary based on the position of its mode in the BEST_MODE_ORDER list.

        Modes not found in the BEST_MODE_ORDER list get sorted to the end of the list.
        """
        mode = seat['type']
        return sort_key_for_mode.get(mode, len(sort_key_for_mode))

    sorted_seats = sorted(seats, key=sort_key)
    if sorted_seats:
        return sorted_seats[0]
    return None


class ReadOnlySerializer(serializers.Serializer):
    """
    A serializer that supports serialization only. Does not support
    deserialization, updates, or creates.
    """
    def to_internal_value(self, data):
        """
        This serializer does not support deserialization.
        """
        raise NotImplementedError

    def create(self, validated_data):
        """
        This serializer does not support creates.
        """
        raise NotImplementedError

    def update(self, instance, validated_data):
        """
        This serializer does not support updates.
        """
        raise NotImplementedError


# pylint: disable=abstract-method
class NormalizedContentMetadataSerializer(ReadOnlySerializer):
    """
    Produces a dict of metadata keys with values calculated
    by normalizing existing key-values. This will be helpful for
    downstream consumers, who should be able to use this dictionary
    instead of doing their own independent normalization.

    Note that course-type-specific definitions of each of these keys may be more nuanced.
    """
    start_date = serializers.SerializerMethodField(help_text='When the course starts')
    end_date = serializers.SerializerMethodField(help_text='When the course ends')
    enroll_by_date = serializers.SerializerMethodField(help_text='The deadline for enrollment')
    content_price = serializers.SerializerMethodField(help_text='The price of a course in USD')

    @cached_property
    def advertised_course_run(self):
        advertised_course_run_uuid = self.instance.json_metadata.get('advertised_course_run_uuid')
        return _get_course_run_by_uuid(self.instance.json_metadata, advertised_course_run_uuid)

    @cached_property
    def additional_metadata(self):
        return self.instance.json_metadata.get('additional_metadata', {})

    @extend_schema_field(serializers.DateTimeField)
    def get_start_date(self, obj) -> str:
        if obj.is_exec_ed_2u_course:
            return self.additional_metadata.get('start_date')

        if not self.advertised_course_run:
            return None

        if start_date_string := self.advertised_course_run.get('start'):
            return start_date_string

        return None

    @extend_schema_field(serializers.DateTimeField)
    def get_end_date(self, obj) -> str:
        if obj.is_exec_ed_2u_course:
            return self.additional_metadata.get('end_date')

        if not self.advertised_course_run:
            return None

        if end_date_string := self.advertised_course_run.get('end'):
            return end_date_string

        return None

    @extend_schema_field(serializers.DateTimeField)
    def get_enroll_by_date(self, obj) -> str:
        if obj.is_exec_ed_2u_course:
            return self.additional_metadata.get('registration_deadline')

        all_seats = self.advertised_course_run.get('seats', [])
        seat = _find_best_mode_seat(all_seats)
        if seat:
            return seat.get('upgrade_deadline')
        else:
            logger.info(
                f"No Seat Found for course run '{self.advertised_course_run.get('key')}'. "
                f"Seats: {all_seats}"
            )
            return None

    @extend_schema_field(serializers.FloatField)
    def get_content_price(self, obj) -> float:
        if obj.is_exec_ed_2u_course:
            for entitlement in obj.json_metadata.get('entitlements', []):
                if entitlement.get('mode') == CourseMode.PAID_EXECUTIVE_EDUCATION:
                    return entitlement.get('price') or DEFAULT_NORMALIZED_PRICE

        return self.advertised_course_run.get('first_enrollable_paid_seat_price') or DEFAULT_NORMALIZED_PRICE
