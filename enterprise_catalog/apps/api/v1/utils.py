import datetime

import pytz
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from six.moves.urllib.parse import (
    parse_qs,
    quote_plus,
    unquote,
    urlencode,
    urlsplit,
    urlunsplit,
)


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
    return {
        'utm_medium': 'enterprise',
        'utm_source': slugify(enterprise_name),
    }


def parse_datetime_handle_invalid(datetime_value):
    """
    Return the parsed version of a datetime string. If the string is invalid, return None.
    """
    try:
        if not isinstance(datetime_value, datetime.datetime):
            datetime_value = parse_datetime(datetime_value)
        return datetime_value.replace(tzinfo=pytz.UTC)
    except TypeError:
        return None


def is_course_run_enrollable(course_run):
    """
    Return true if the course run is enrollable, false otherwise.

    We look for the following criteria:
    1. end date is greater than a reasonably-defined enrollment window, or undefined
       * reasonably-defined enrollment window is 1 day before course run end date
    2. enrollment_start is less than now, or undefined
    3. enrollment_end is greater than now, or undefined
    """
    now = datetime.datetime.now(pytz.UTC)
    reasonable_enrollment_window = now + datetime.timedelta(days=1)
    end = parse_datetime_handle_invalid(course_run.get('end'))
    enrollment_start = parse_datetime_handle_invalid(course_run.get('enrollment_start'))
    enrollment_end = parse_datetime_handle_invalid(course_run.get('enrollment_end'))
    return (not end or end > reasonable_enrollment_window) and \
           (not enrollment_start or enrollment_start < now) and \
           (not enrollment_end or enrollment_end > now)


def is_course_run_available_for_enrollment(course_run):
    """
    Check if a course run is available for enrollment.
    """
    if course_run['availability'] not in ['Current', 'Starting Soon', 'Upcoming']:
        # course run is archived so not available for enrollment
        return False

    # now check if the course run is enrollable on the basis of enrollment
    # start and end date
    return is_course_run_enrollable(course_run)


def has_course_run_available_for_enrollment(course_runs):
    """
    Iterates over all course runs to check if there any course run that is available for enrollment.

    :param course_runs: list of course runs
    :returns True if found else false
    """
    for course_run in course_runs:
        if is_course_run_available_for_enrollment(course_run):
            return True
    return False
