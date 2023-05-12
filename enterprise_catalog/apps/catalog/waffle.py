"""
This module contains various configuration settings via
waffle switches for the catalog app.
"""

from edx_toggles.toggles import WaffleFlag, WaffleSwitch


WAFFLE_NAMESPACE = 'catalog'

DISABLE_MODEL_ADMIN_CHANGES = 'disable_model_admin_changes'
LEARNER_PORTAL_ENROLLMENT_ALL_SUBSIDIES_AND_CONTENT_TYPES = 'learner_portal_enrollment_all_subsidies_and_content_types'

# .. toggle_name: catalog.disable_model_admin_changes
# .. toggle_implementation: WaffleSwitch
# .. toggle_default: False
# .. toggle_description: Indicates whether or not to disable Django admin changes for configured models.
# .. toggle_use_cases: opt_in
# .. toggle_creation_date: 2021-03-25
DISABLE_MODEL_ADMIN_CHANGES_SWITCH = WaffleSwitch(
    f'{WAFFLE_NAMESPACE}.{DISABLE_MODEL_ADMIN_CHANGES}',
    module_name=__name__,
)

# .. toggle_name: catalog.learner_portal_enrollment_all_subsidies_and_content_types
# .. toggle_implementation: WaffleFlag
# .. toggle_default: False
# .. toggle_description: Indicates whether enrollment urls should point to learner portal for all customers, subsidies, and content types for customers with learner portal enabled.
# .. toggle_use_cases: opt_in
# .. toggle_creation_date: 2023-05-15
LEARNER_PORTAL_ENROLLMENT_ALL_SUBSIDIES_AND_CONTENT_TYPES_FLAG = WaffleFlag(
    f'{WAFFLE_NAMESPACE}.{LEARNER_PORTAL_ENROLLMENT_ALL_SUBSIDIES_AND_CONTENT_TYPES}',
    module_name=__name__,
)


def use_learner_portal_for_all_subsidies_content_types():
    """
    Returns whether enrollments url should point to learner portal for all customers,
    subsidies, and content types for customers with learner portal enabled.
    """
    return LEARNER_PORTAL_ENROLLMENT_ALL_SUBSIDIES_AND_CONTENT_TYPES_FLAG.is_enabled()
