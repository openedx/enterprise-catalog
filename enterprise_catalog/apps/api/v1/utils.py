import logging

from algoliasearch.search_client import SearchClient
from django.utils.text import slugify
from langcodes import Language
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


def is_any_course_run_enrollable(course_runs):
    """
    Iterates over all course runs to check if there any course run that is available for enrollment.

    Arguments:
        course_runs (list): list of course runs

    Returns:
        bool: True if enrollable course run is found, else False
    """
    for course_run in course_runs:
        if course_run.get('is_enrollable'):
            return True
    return False


def initialize_algolia_index(index_name, app_id, api_key):
    """
    Creates an Algolia client and initializes an index with the given name.

    Initializing an index will create it if it does not yet exist.

    Arguments:
        index_name (str): name of the Algolia index
        app_id (str): APPLICATION_ID to connect to Algolia
        api_key (str): API_KEY to connect to Algolia

    Returns:
        dict: an Algolia index or None if we cannot initialize an Algolia index
    """
    if not index_name:
        logger.error('Could not initialize Algolia index due to missing index name.')
        # can't do much without an index_name, so return None
        return None

    algolia_client = None
    if app_id and api_key:
        algolia_client = SearchClient.create(app_id, api_key)
        if algolia_client:
            return algolia_client.init_index(index_name)

    logger.error(
        'Could not initialize Algolia\'s %s index due to missing Algolia settings: %s',
        index_name,
        ['APPLICATION_ID', 'API_KEY'],
    )
    return None


def get_algolia_object_id(uuid):
    """
    Given a uuid, returns an object_id to use for Algolia indexing.

    Arguments:
        uuid (str): a course uuid

    Returns:
        str: the generated Algolia object_id
    """
    object_id = 'course-{}'.format(uuid)
    return object_id


def add_uuids_to_courses(content_key, uuids, courses):
    """
    Adds associated enterprise_catalog_uuids and enterprise_customer_uuids to a course.

    Arguments:
        content_key (str): content_key of a course that we want to add uuids for
        uuids (dict): a dictionary containing both enterprise_catalog_uuids and enterprise_customer_uuids
        courses (list): a list of courses

    Returns:
        list: a list of courses with the uuids added on to the appropriate course
    """
    # find index in courses where course key matches content_key
    course_index = next(
        (index for (index, d) in enumerate(courses) if d['key'] == content_key),
        None
    )
    if course_index is not None:
        course = courses[course_index].copy()
        course.update({
            'objectID': get_algolia_object_id(course['uuid']),
            'enterprise_catalog_uuids': uuids.get('enterprise_catalog_uuids', []),
            'enterprise_customer_uuids': uuids.get('enterprise_customer_uuids', []),
        })
        courses[course_index] = course
    else:
        logger.error(
            'Could not find course with content key %s from course-discovery discovery',
            content_key,
        )

    return courses


def get_course_language(course_runs):
    """
    Gets the languages associated with a course.

    Arguments:
        course_runs (list): list of course runs for a course

    Returns:
        list: a list of supported languages for those course runs
    """
    languages = set()

    for course_run in course_runs:
        content_language = course_run.get('content_language')
        if not content_language:
            continue
        language_name = Language.make(language=content_language).language_name()
        languages.add(language_name)

    return list(languages)


def get_course_availability(course_runs):
    """
    Gets the availability for a course.

    Arguments:
        course_runs (list): list of course runs for a course

    Returns:
        list: a list of availabilities for those course runs (e.g., "Upcoming")
    """
    availability = set()

    for course_run in course_runs:
        run_availability = course_run.get('availability', '').lower()
        if run_availability == 'current':
            availability.add('Available now')
        elif run_availability == 'upcoming':
            availability.add('Upcoming')
        else:
            availability.add('Archived')

    return list(availability)


def get_algolia_object_from_course(course, algolia_fields):
    """
    Transforms a course into an Algolia object.

    Arguments:
        course (dict): a course dict
        algolia_fields (list): list of fields to extract from the course

    Returns:
        dict: a dictionary containing only the fields noted in algolia_fields
    """
    course = course.copy()
    published_course_runs = list(
        filter(lambda d: d['status'].lower() == 'published', course.get('course_runs', []))
    )
    course.update({
        'language': get_course_language(published_course_runs),
        'availability': get_course_availability(published_course_runs),
    })

    algolia_object = {}
    for field in algolia_fields:
        algolia_object[field] = course.get(field)

    return algolia_object


def create_algolia_objects_from_courses(courses, algolia_fields):
    """
    Transforms all courses into Algolia objects.

    Arguments:
        courses (list): list of courses
        algolia_fields (list): list of fields to extract from courses

    Returns:
        list: a list of Algolia objects containing only the fields noted in algolia_fields
    """
    if not algolia_fields:
        algolia_fields = []

    algolia_objects = []
    for course in courses:
        algolia_objects.append(get_algolia_object_from_course(course, algolia_fields))

    return algolia_objects
