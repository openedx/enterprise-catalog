"""
Defines serializers to process data at the boundaries
of the `catalog` domain.
"""
import logging

from django.utils.functional import cached_property
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from enterprise_catalog.apps.api.constants import CourseMode
from enterprise_catalog.apps.catalog.constants import EXEC_ED_2U_COURSE_TYPE
from enterprise_catalog.apps.catalog.utils import get_course_run_by_uuid


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

    The serializer expects the following keys in the input dictionary:
    - course: a ContentMetadata object representing the course
    - [course_run_metadata]: Optionally, a dictionary representing a specific course run's metadata

    When no course run metadata is provided, the serializer will attempt to use the course's advertised course run
    metadata. If that is not available, the serializer will return None for all fields.

    Note that course-type-specific definitions of each of these keys may be more nuanced.
    """

    start_date = serializers.SerializerMethodField(help_text='When the course starts')
    end_date = serializers.SerializerMethodField(help_text='When the course ends')
    enroll_by_date = serializers.SerializerMethodField(help_text='The deadline for enrollment')
    enroll_start_date = serializers.SerializerMethodField(help_text='The date when enrollment starts')
    content_price = serializers.SerializerMethodField(help_text='The price of a course in USD')

    @cached_property
    def course_metadata(self):
        return self.instance.get('course_metadata')

    @cached_property
    def is_exec_ed_2u_course(self):
        return self.course_metadata.get('course_type') == EXEC_ED_2U_COURSE_TYPE

    @cached_property
    def course_run_metadata(self):
        if run_metadata := self.instance.get('course_run_metadata'):
            return run_metadata
        advertised_course_run_uuid = self.course_metadata.get('advertised_course_run_uuid')
        return get_course_run_by_uuid(self.course_metadata, advertised_course_run_uuid)

    @extend_schema_field(serializers.DateTimeField)
    def get_start_date(self, obj) -> str:  # pylint: disable=unused-argument
        if not self.course_run_metadata:
            return None
        return self.course_run_metadata.get('start')

    @extend_schema_field(serializers.DateTimeField)
    def get_end_date(self, obj) -> str:  # pylint: disable=unused-argument
        if not self.course_run_metadata:
            return None
        return self.course_run_metadata.get('end')

    @extend_schema_field(serializers.DateTimeField)
    def get_enroll_start_date(self, obj) -> str:  # pylint: disable=unused-argument
        if not self.course_run_metadata:
            return None
        return self.course_run_metadata.get('enrollment_start')

    @extend_schema_field(serializers.DateTimeField)
    def get_enroll_by_date(self, obj) -> str:  # pylint: disable=unused-argument
        if not self.course_run_metadata:
            return None

        if self.is_exec_ed_2u_course:
            return self.course_run_metadata.get('enrollment_end')

        all_seats = self.course_run_metadata.get('seats', [])

        upgrade_deadline = None
        if seat := _find_best_mode_seat(all_seats):
            upgrade_deadline = seat.get('upgrade_deadline_override') or seat.get('upgrade_deadline')

        enrollment_end = self.course_run_metadata.get('enrollment_end')
        return min(filter(None, [upgrade_deadline, enrollment_end]), default=None)

    @extend_schema_field(serializers.FloatField)
    def get_content_price(self, obj) -> float:  # pylint: disable=unused-argument
        if not self.course_run_metadata:
            return None
        if self.course_run_metadata.get('fixed_price_usd'):
            return float(self.course_run_metadata.get('fixed_price_usd'))
        if self.is_exec_ed_2u_course is True:
            for entitlement in self.course_metadata.get('entitlements', []):
                if entitlement.get('price') and entitlement.get('mode') == CourseMode.PAID_EXECUTIVE_EDUCATION:
                    return float(entitlement.get('price'))
        if self.course_run_metadata.get('first_enrollable_paid_seat_price'):
            return float(self.course_run_metadata.get('first_enrollable_paid_seat_price'))
        return DEFAULT_NORMALIZED_PRICE
