import logging

from django.utils.text import slugify
from six.moves.urllib.parse import (
    parse_qs,
    quote_plus,
    unquote,
    urlencode,
    urlsplit,
    urlunsplit,
)


logger = logging.getLogger(__name__)


def unquote_course_keys(course_keys):
    """
    Maintain plus characters in course/course run keys from query parameters
    """
    return [unquote(quote_plus(course_key)) for course_key in course_keys]


def update_query_parameters(url, query_parameters):
    """
    Return url with updated query parameters.

    Arguments:
        url (str): Original url whose query parameters need to be updated.
        query_parameters (dict): A dictionary containing query parameters to be added to course selection url.

    Returns:
        (slug): slug identifier for the identity provider that can be used for identity verification of
            users associated the enterprise customer of the given user.

    """
    scheme, netloc, path, query_string, fragment = urlsplit(url)
    url_params = parse_qs(query_string)

    # Update url query parameters
    url_params.update(query_parameters)

    return urlunsplit(
        (scheme, netloc, path, urlencode(sorted(url_params.items()), doseq=True), fragment),
    )


def get_enterprise_utm_context(enterprise_name):
    """
    Get the UTM context for the enterprise.
    """
    utm_context = {
        'utm_medium': 'enterprise',
    }

    if enterprise_name:
        utm_context['utm_source'] = slugify(enterprise_name)

    return utm_context


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


def is_any_course_run_active(course_runs):
    """
    Iterates over all course runs to check if there any course run that is available for enrollment.

    Arguments:
        course_runs (list): list of course runs

    Returns:
        bool: True if active course run is found, else False
    """
    for course_run in course_runs:
        if is_course_run_active(course_run):
            return True
    return False


def get_most_recent_modified_time(content_modified, catalog_modified=None, customer_modified=None):
    """
    Helper function to get the appropriate content last modified time for a content metadata object under a specific
    customer
    """
    if catalog_modified:
        content_modified = max([content_modified, catalog_modified])
    if customer_modified:
        content_modified = max([content_modified, customer_modified])
    return content_modified


def get_archived_content_count(highlighted_content):
    """
    Helper function to get the count of archived content from a highlight set
    """
    archived_content_count = 0
    for content in highlighted_content:
        course_run_statuses = content.course_run_statuses
        if course_run_statuses and all(status in ('archived', 'unpublished') for status in course_run_statuses):
            archived_content_count += 1
    return archived_content_count
