import json

from enterprise_catalog.apps.catalog.waffle import (
    DISABLE_MODEL_ADMIN_CHANGES_SWITCH,
)


# ContentMetadata content_type choices
COURSE = 'course'
COURSE_RUN = 'courserun'
PROGRAM = 'program'
LEARNER_PATHWAY = 'learnerpathway'

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
# 'executive-education'
# 'executive-education-2u'
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

SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE = 'enterprise_catalog_admin'
SYSTEM_ENTERPRISE_LEARNER_ROLE = 'enterprise_learner'
SYSTEM_ENTERPRISE_ADMIN_ROLE = 'enterprise_admin'
SYSTEM_ENTERPRISE_OPERATOR_ROLE = 'enterprise_openedx_operator'

ACCESS_TO_ALL_ENTERPRISES_TOKEN = '*'

PERMISSION_HAS_LEARNER_ACCESS = 'catalog.has_learner_access'
PERMISSION_HAS_ADMIN_ACCESS = 'catalog.has_admin_access'

DISCOVERY_COURSE_KEY_BATCH_SIZE = 50
DISCOVERY_PROGRAM_KEY_BATCH_SIZE = 50

# Async task constants
REINDEX_TASK_BATCH_SIZE = 10
TASK_BATCH_SIZE = 250
TASK_TIMEOUT = 2 * 60 * 60  # Gives tasks (usually chains) 2 hours to return before timing out

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
