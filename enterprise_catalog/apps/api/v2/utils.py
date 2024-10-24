import logging

from enterprise_catalog.apps.catalog.constants import (
    COURSE_RUN_RESTRICTION_TYPE_KEY,
    RESTRICTION_FOR_B2B,
)


logger = logging.getLogger(__name__)


def is_course_run_active(course_run):
    """
    Checks whether a course run is active. That is, whether the course run is published,
    enrollable, and either marketable, or has a b2b restriction type. To ellaborate on the latter:

    Restricted course run records will be set with `is_marketable: false` from the
    upstream source-of-truth (course-discovery).  But because our discovery <-> catalog
    synchronization has business logic that filters course run json metadata (inside of courses)
    to only the *allowed* restricted runs for a catalog, we can safely assume
    when looking at a course run metadata record in the context of a catalog,
    if that run has a non-null, B2B restriction type, then it is permitted to be
    part of the catalog and should be considered active (as long as it is published and enrollable).

    Arguments:
        course_run (dict): The metadata about a course run.

    Returns:
        bool: True if the course run is "active"
    """
    course_run_status = course_run.get('status') or ''
    is_published = course_run_status.lower() == 'published'
    is_enrollable = course_run.get('is_enrollable', False)
    is_marketable = course_run.get('is_marketable', False)
    is_restricted = course_run.get(COURSE_RUN_RESTRICTION_TYPE_KEY) == RESTRICTION_FOR_B2B

    return is_published and is_enrollable and (is_marketable or is_restricted)


def is_any_course_run_active(course_runs):
    """
    Iterates over all course runs to check if there's any course run that is available for enrollment.

    Arguments:
        course_runs (list): list of course runs

    Returns:
        bool: True if active course run is found, else False
    """
    for course_run in course_runs:
        if is_course_run_active(course_run):
            return True
    return False
