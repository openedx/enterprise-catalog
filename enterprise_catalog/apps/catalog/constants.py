import json

from enterprise_catalog.apps.catalog.waffle import (
    DISABLE_MODEL_ADMIN_CHANGES_SWITCH,
)


# ContentMetadata content_type choices
COURSE = 'course'
COURSE_RUN = 'courserun'
PROGRAM = 'program'
CONTENT_TYPE_CHOICES = [
    (COURSE, 'Course'),
    (COURSE_RUN, 'Course Run'),
    (PROGRAM, 'Program'),
]

# ContentFilter field types for validation.
CONTENT_FILTER_FIELD_TYPES = {
    'key': {'type': list, 'subtype': str},
    'first_enrollable_paid_seat_price__lte': {'type': str}
}

# Course mode sorting based on slug
COURSE_MODE_SORT_ORDER = ['verified', 'professional', 'no-id-professional', 'audit', 'honor']

ENTERPRISE_CATALOG_ADMIN_ROLE = 'enterprise_catalog_admin'
ENTERPRISE_CATALOG_LEARNER_ROLE = 'enterprise_learner'

SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE = 'enterprise_catalog_admin'
SYSTEM_ENTERPRISE_LEARNER_ROLE = 'enterprise_learner'
SYSTEM_ENTERPRISE_ADMIN_ROLE = 'enterprise_admin'
SYSTEM_ENTERPRISE_OPERATOR_ROLE = 'enterprise_openedx_operator'

ACCESS_TO_ALL_ENTERPRISES_TOKEN = '*'

DISCOVERY_COURSE_KEY_BATCH_SIZE = 50
DISCOVERY_PROGRAM_KEY_BATCH_SIZE = 50

# Async task constants
TASK_BATCH_SIZE = 250
TASK_TIMEOUT = 90 * 60  # Gives tasks (usually chains) 90 minutes to return before timing out

# Which fields should be plucked from the /search/all course-discovery API
# response in `update_catalog_metadata_task` for course content metadata?
DEFAULT_COURSE_FIELDS_TO_PLUCK_FROM_SEARCH_ALL = [
    'aggregation_key',
    'content_type',
    'seat_types',
    'end_date',
    'course_ends',
    'languages',
]


def json_serialized_course_modes():
    """
    :return: serialized course modes.
    """
    return json.dumps(COURSE_MODE_SORT_ORDER)


def admin_model_changes_allowed():
    """
    Returns whether changes are allowed to a model based off the disable_model_admin_changes switch
    """
    return not DISABLE_MODEL_ADMIN_CHANGES_SWITCH.is_enabled()
