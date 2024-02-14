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
