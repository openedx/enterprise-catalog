"""
Utility functions for manipulating content metadata.
"""

from logging import getLogger

from enterprise_catalog.apps.catalog.utils import get_content_key

from .constants import FORCE_INCLUSION_METADATA_TAG_KEY


LOGGER = getLogger(__name__)


def tansform_force_included_courses(courses):
    """
    Transform a list of forced/unlisted course metadata
    ENT-8212
    """
    results = []
    for course_metadata in courses:
        results.append(transform_course_metadata_to_visible(course_metadata))
    return results


def transform_course_metadata_to_visible(course_metadata):
    """
    Transform an individual forced/unlisted course metadata
    so that it is visible/available/published in our metadata
    ENT-8212
    """
    content_key = get_content_key(course_metadata)
    LOGGER.info(
        f'transform_course_metadata_to_visible on content_key: {content_key}'
    )
    course_metadata[FORCE_INCLUSION_METADATA_TAG_KEY] = True
    course_run_statuses = []
    for course_run in course_metadata.get('course_runs', []):
        course_run['status'] = 'published'
        course_run['availability'] = 'Current'
        course_run_statuses.append(course_run.get('status'))
    course_metadata['course_run_statuses'] = course_run_statuses
    return course_metadata


def get_course_run_by_uuid(course, course_run_uuid):
    """
    Find a course_run based on uuid
    Arguments:
        course (dict): course dict
        course_run_uuid (str): uuid to lookup
    Returns:
        dict: a course_run or None
    """
    try:
        course_run = [
            run for run in course.get('course_runs', [])
            if run.get('uuid') == course_run_uuid
        ][0]
    except IndexError:
        return None
    return course_run


def is_course_run_active(course_run):
    """
    Checks whether a course run is active. That is, whether the course run is published,
    enrollable, and marketable.
    Arguments:
        course_run (dict): The metadata about a course run.
    Returns:
        bool: True if course run is "active"
    """
    is_enrollable = course_run.get('is_enrollable', False)
    if course_run.get("is_marketable_external") and is_enrollable:
        return True
    course_run_status = course_run.get('status') or ''
    is_published = course_run_status.lower() == 'published'
    is_marketable = course_run.get('is_marketable', False)

    return is_published and is_enrollable and is_marketable


def get_course_first_paid_enrollable_seat_price(course):
    """
    Arguments:
        course (dict): a dictionary representing a course
    Returns:
        The first enrollable paid seat price for the course.
    """
    # Use advertised course run.
    # If that fails use one of the other active course runs.
    # (The latter is what Discovery does)
    advertised_course_run = get_advertised_course_run(course)
    if advertised_course_run and advertised_course_run.get('first_enrollable_paid_seat_price'):
        return advertised_course_run.get('first_enrollable_paid_seat_price')

    course_runs = course.get('course_runs') or []
    active_course_runs = [run for run in course_runs if is_course_run_active(run)]
    for course_run in sorted(
        active_course_runs,
        key=lambda active_course_run: active_course_run['key'].lower(),
    ):
        if 'first_enrollable_paid_seat_price' in course_run:
            return course_run['first_enrollable_paid_seat_price']
    return None


def get_advertised_course_run(course):
    """
    Get part of the advertised course_run as per advertised_course_run_uuid

    Argument:
        course (dict)

    Returns:
        dict: containing key, pacing_type, start, end, and upgrade deadline
        for the course_run, or None
    """
    full_course_run = get_course_run_by_uuid(course, course.get('advertised_course_run_uuid'))
    if full_course_run is None:
        return None
    return full_course_run
