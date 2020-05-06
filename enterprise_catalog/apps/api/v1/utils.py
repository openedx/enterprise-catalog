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
    utm_context = {
        'utm_medium': 'enterprise',
    }

    if enterprise_name:
        utm_context['utm_source'] = slugify(enterprise_name)

    return utm_context


def is_any_course_run_enrollable(course_runs):
    """
    Iterates over all course runs to check if there any course run that is available for enrollment.

    Arguments:
            course_runs (list): list of course runs

    Returns:
        bool: True if enrollable course run is found, else False
    """
    for course_run in course_runs:
        if course_run['is_enrollable']:
            return True
    return False
