"""
Utility functions for manipulating content metadata.
"""

from logging import getLogger

from enterprise_catalog.apps.catalog.utils import get_content_key

from .constants import (
    COURSE_RUN_RESTRICTION_TYPE_KEY,
    FORCE_INCLUSION_METADATA_TAG_KEY,
)


LOGGER = getLogger(__name__)


def transform_force_included_courses(courses):
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
    course_run_status = course_run.get('status') or ''
    is_published = course_run_status.lower() == 'published'
    is_enrollable = course_run.get('is_enrollable', False)
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
    advertised_course_run = get_course_run_by_uuid(course, course.get('advertised_course_run_uuid'))
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


def find_restricted_course_runs(course_json_metadata):
    """
    Filter to find and enumerate any restricted runs present in a dictionary
    of course JSON metadata.
    """
    found_restricted_runs = []
    for course_run in course_json_metadata.get('course_runs', []):
        if course_run.get(COURSE_RUN_RESTRICTION_TYPE_KEY):
            found_restricted_runs.append(course_run)
    return found_restricted_runs


def remove_restricted_course_runs(course_json_metadata):
    """
    Prevents restricted runs from being written to ContentMetadata.json_metadata before saving.
    This includes removing the run from all run-based json keys:
    * ContentMetadata.json_metadata["course_runs"]
    * ContentMetadata.json_metadata["course_run_keys"]
    * ContentMetadata.json_metadata["course_run_statuses"]

    It also updates the `first_enrollable_paid_seat_price` of the course after restricted runs
    are removed.
    """
    found_restricted_runs = find_restricted_course_runs(course_json_metadata)
    if not found_restricted_runs:
        return

    restricted_keys = {run['key'] for run in found_restricted_runs}
    LOGGER.info(
        '[restricted runs] Course %s has restricted runs %s that will be removed.',
        course_json_metadata['key'],
        restricted_keys,
    )

    non_restricted_keys = []
    non_restricted_runs = []
    non_restricted_statuses = set()

    for course_run in course_json_metadata['course_runs']:
        if course_run['key'] not in restricted_keys:
            non_restricted_keys.append(course_run['key'])
            non_restricted_runs.append(course_run)
            non_restricted_statuses.add(course_run['status'])

    course_json_metadata['course_runs'] = non_restricted_runs
    course_json_metadata['course_run_keys'] = non_restricted_keys
    course_json_metadata['course_run_statuses'] = sorted(list(non_restricted_statuses))

    # also recompute the first enrollable paid seat price for the course
    # now that we've removed any restricted runs
    course_json_metadata['first_enrollable_paid_seat_price'] = get_course_first_paid_enrollable_seat_price(
        course_json_metadata,
    )
