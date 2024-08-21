"""
Python interface for the ``catalog`` module.
"""
from collections import defaultdict

from enterprise_catalog.apps.catalog.constants import COURSE_RUN_KEY_PREFIX


def get_restricted_runs_allowed_for_query(course_run_ids, customer_catalogs):
    """
    Filter the set of restricted course keys down to only
    those requested in ``course_run_ids``.

    Params:
        course_run_ids: A list of either course or course run keys.
        customer_catalogs: A list of ``EnterpriseCatalog`` records.

    Returns:
        A dictionary mapping courses to allowed restricted runs for catalogs that
        allow the restricted inclusion. That is:
        ```
        {
            'org+key1': {
                'course-v1:org+key1+restrictedrun': {
                    'catalog_uuids': {'catalog-1.uuid'}
                },
            },
            'org+key3': {
                'course-v1:org+key3+restrictedrun': {
                    'catalog_uuids': {'catalog-2.uuid'}
                },
            },
        }
        ```
    """
    requested_course_keys = {
        key for key in course_run_ids if not key.startswith(COURSE_RUN_KEY_PREFIX)
    }
    requested_run_keys = {
        key for key in course_run_ids if key.startswith(COURSE_RUN_KEY_PREFIX)
    }
    serialized_data = defaultdict(lambda: defaultdict(lambda: {'catalog_uuids': set()}))
    for catalog in customer_catalogs:
        if not catalog.restricted_runs_allowed:
            continue

        for restricted_course_key, restricted_runs in catalog.restricted_runs_allowed.items():
            matching_runs = bool(set(restricted_runs).intersection(requested_run_keys))
            matching_course = restricted_course_key in requested_course_keys
            if not (matching_course or matching_runs):
                continue

            course_dict = serialized_data[restricted_course_key]
            for course_run_key in restricted_runs:
                run_dict = course_dict[course_run_key]
                run_dict['catalog_uuids'].add(str(catalog.uuid))
    return serialized_data or None


def catalog_contains_any_restricted_course_run(enterprise_catalog, course_run_keys):
    """
    Params:
        course_run_keys: A list of candidate course run keys.
        customer_catalog: An ``EnterpriseCatalog`` record.

    Returns:
        A boolean indicating if at least one of the provided course_run_keys
        is present in the set of restricted runs for the given enterprise_catalog.
    """
    for course_run_key in course_run_keys:
        if course_run_key in enterprise_catalog.restricted_courses_by_run_key:
            return True
    return False
