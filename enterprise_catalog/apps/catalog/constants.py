import json

import waffle


# Waffle Switches
DISABLE_MODEL_ADMIN_CHANGES = 'disable_model_admin_changes'

# ContentMetadata content_type choices
COURSE = 'course'
COURSE_RUN = 'courserun'
PROGRAM = 'program'
CONTENT_TYPE_CHOICES = [
    (COURSE, 'Course'),
    (COURSE_RUN, 'Course Run'),
    (PROGRAM, 'Program'),
]

# Course mode sorting based on slug
COURSE_MODE_SORT_ORDER = ['verified', 'professional', 'no-id-professional', 'audit', 'honor']

ENTERPRISE_CATALOG_ADMIN_ROLE = 'enterprise_catalog_admin'
ENTERPRISE_ADMIN_ROLE = 'enterprise_admin'
ENTERPRISE_OPERATOR_ROLE = 'enterprise_openedx_operator'


def json_serialized_course_modes():
    """
    :return: serialized course modes.
    """
    return json.dumps(COURSE_MODE_SORT_ORDER)

def admin_model_changes_allowed():
    """
    Returns whether changes are allowed to a model based off the disable_model_admin_changes switch
    """
    return not waffle.switch_is_active(DISABLE_MODEL_ADMIN_CHANGES)
