"""
This module contains various configuration settings via
waffle switches for the catalog app.
"""

from edx_toggles.toggles import WaffleSwitch


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
