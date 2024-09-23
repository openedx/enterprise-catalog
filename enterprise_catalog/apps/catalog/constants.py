import json
from datetime import datetime

from enterprise_catalog.apps.catalog.waffle import (
    DISABLE_MODEL_ADMIN_CHANGES_SWITCH,
)


# Algolia timestamp default
ALGOLIA_DEFAULT_TIMESTAMP = (datetime(3000, 1, 1)).timestamp()

# ContentMetadata content_type choices
COURSE = 'course'
COURSE_RUN = 'courserun'
PROGRAM = 'program'
LEARNER_PATHWAY = 'learnerpathway'
VIDEO = 'video'

CONTENT_TYPE_CHOICES = [
    (COURSE, 'Course'),
    (COURSE_RUN, 'Course Run'),
    (PROGRAM, 'Program'),
    (LEARNER_PATHWAY, 'Learner Pathway'),
]

EXEC_ED_2U_COURSE_TYPE = 'executive-education-2u'
EXEC_ED_2U_READABLE_COURSE_TYPE = 'Executive Education'
EXEC_ED_2U_ENTITLEMENT_MODE = 'paid-executive-education'

# ContentMetadata allow/block lists

# deliberate omissions:
# 'bootcamp-2u'
# 'empty'

CONTENT_COURSE_TYPE_ALLOW_LIST = {
    'audit',
    'professional',
    'verified-audit',
    'credit-verified-audit',
    'masters',
    'masters-verified-audit',
    'verified',
    'spoc-verified-audit',
    'honor',
    'verified-honor',
    'credit-verified-honor',
    'executive-education-2u',
}

# deliberate omissions:
# 'emeritus'

CONTENT_PRODUCT_SOURCE_ALLOW_LIST = {
    '2u',
    'edx',
}

# ContentFilter field types for validation.
CONTENT_FILTER_FIELD_TYPES = {
    'key': {'type': list, 'subtype': str},
    'first_enrollable_paid_seat_price__lte': {'type': str}
}

# Course mode sorting based on slug
COURSE_MODE_SORT_ORDER = ['verified', 'professional', 'no-id-professional', 'audit', 'honor']

ENTERPRISE_CATALOG_ADMIN_ROLE = 'enterprise_catalog_admin'
ENTERPRISE_CATALOG_LEARNER_ROLE = 'enterprise_learner'
ENTERPRISE_CATALOG_PROVISIONING_ADMIN = 'enterprise_catalog_provisioning_admin'

SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE = 'enterprise_catalog_admin'
SYSTEM_ENTERPRISE_LEARNER_ROLE = 'enterprise_learner'
SYSTEM_ENTERPRISE_ADMIN_ROLE = 'enterprise_admin'
SYSTEM_ENTERPRISE_OPERATOR_ROLE = 'enterprise_openedx_operator'
SYSTEM_ENTERPRISE_PROVISIONING_ADMIN_ROLE = 'enterprise_provisioning_admin'

ACCESS_TO_ALL_ENTERPRISES_TOKEN = '*'

PERMISSION_HAS_LEARNER_ACCESS = 'catalog.has_learner_access'
PERMISSION_HAS_ADMIN_ACCESS = 'catalog.has_admin_access'
PERMISSION_HAS_PROVISIONING_ADMIN_ACCESS = 'catalog.has_provisioning_admin_access'

DISCOVERY_COURSE_KEY_BATCH_SIZE = 50
DISCOVERY_PROGRAM_KEY_BATCH_SIZE = 50

# Async task constants
REINDEX_TASK_BATCH_SIZE = 10
TASK_BATCH_SIZE = 250
TASK_TIMEOUT = 3 * 60 * 60  # Gives tasks (usually chains) 3 hours to return before timing out

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

PROGRAM_TYPES_MAP = {
    'XSeries': 'XSeries Program',
    'MicroMasters': 'MicroMasters® Program',
    'Professional Certificate': 'Professional Certificate',
    'Professional Program': 'Professional Program',
    'Masters': "Master's Degree Program",
    'MicroBachelors': 'MicroBachelors® Program',
    'Certificación Profesional': 'Certificación Profesional',
}

FORCE_INCLUSION_METADATA_TAG_KEY = 'enterprise_force_included'

# Late enrollment threshold
LATE_ENROLLMENT_THRESHOLD_DAYS = 30

RESTRICTED_RUNS_ALLOWED_KEY = 'restricted_runs_allowed'

AGGREGATION_KEY_PREFIX = 'course:'

COURSE_RUN_KEY_PREFIX = 'course-v1:'

COURSE_RUN_RESTRICTION_TYPE_KEY = 'restriction_type'


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
