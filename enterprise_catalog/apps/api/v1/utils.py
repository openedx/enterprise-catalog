import copy
import logging

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


def get_algolia_object_id(uuid):
    """
    Given a uuid, returns an object_id to use for Algolia indexing.

    Arguments:
        uuid (str): a course uuid

    Returns:
        str: the generated Algolia object_id or None if uuid is not specified
    """
    if uuid:
        return 'course-{}'.format(uuid)
    return None


def get_course_language(course_runs):
    """
    Gets the languages associated with a course. Used for the "Language" facet in Algolia.

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
    Gets the availability for a course. Used for the "Availability" facet in Algolia.

    Arguments:
        course_runs (list): list of course runs for a course

    Returns:
        list: a list of availabilities for those course runs (e.g., "Upcoming")
    """
    DEFAULT_COURSE_AVAILABILITY = 'Archived'
    COURSE_AVAILABILITY_MESSAGES = {
        'current': 'Available Now',
        'upcoming': 'Upcoming',
    }

    availability = set()

    for course_run in course_runs:
        run_availability = course_run.get('availability', '').lower()
        availability.add(
            COURSE_AVAILABILITY_MESSAGES.get(run_availability, DEFAULT_COURSE_AVAILABILITY)
        )

    return list(availability)


def get_course_partners(course):
    """
    Gets list of partners associated with the course. Used for the "Partners" facet and
    searchable attribute in Algolia.

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        list: a list of partner metadata associated with the course
    """
    partners = []
    owners = course.get('owners') or []

    for owner in owners:
        partner_name = owner.get('name')
        if partner_name:
            partner_metadata = {
                'name': partner_name,
                'logo_image_url': owner.get('logo_image_url'),
            }
            partners.append(partner_metadata)

    return partners


def get_course_program_types(course):
    """
    Gets list of program types associated with the course. Used for the "Programs"
    facet in Algolia.

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        list: a list of program types associated with the course
    """
    program_types = set()
    programs = course.get('programs', [])

    for program in programs:
        program_type = program.get('type')
        if program_type:
            program_types.add(program_type)

    return list(program_types)


def get_course_subjects(course):
    """
    Gets list of subject names associated with the course. Used for the "Subjects"
    facet in Algolia.

    `course.get('subjects')` may be either:
        - a list of strings, e.g. ['Communication']
        - a list of dictionaries, e.g. [{'name': 'Communication'}]

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        list: a list of subject names associated with the course
    """
    subject_names = set()
    subjects = course.get('subjects') or []

    for subject in subjects:
        if isinstance(subject, str):
            subject_names.add(subject)
            continue

        subject_name = subject.get('name')
        if subject_name:
            subject_names.add(subject_name)

    return list(subject_names)


def get_course_card_image_url(course):
    """
    Gets the appropriate image to use for course cards.

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        str: the url for the course card image
    """
    original_image = course.get('original_image')
    if original_image:
        return original_image.get('src')
    return None


def _algolia_object_from_course(course, algolia_fields):
    """
    Transforms a course into an Algolia object.

    Arguments:
        course (dict): a course dict
        algolia_fields (list): list of fields to extract from the course

    Returns:
        dict: a dictionary containing only the fields noted in algolia_fields
    """
    searchable_course = copy.deepcopy(course)
    published_course_runs = [
        course_run for course_run in searchable_course.get('course_runs', [])
        if course_run.get('status', '').lower() == 'published'
    ]
    searchable_course.update({
        'language': get_course_language(published_course_runs),
        'availability': get_course_availability(published_course_runs),
        'partners': get_course_partners(searchable_course),
        'programs': get_course_program_types(searchable_course),
        'subjects': get_course_subjects(searchable_course),
        'card_image_url': get_course_card_image_url(searchable_course),
    })

    algolia_object = {}
    for field in algolia_fields:
        field_value = searchable_course.get(field)
        if field_value:
            algolia_object[field] = field_value

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

    algolia_objects = [
        _algolia_object_from_course(course, algolia_fields)
        for course in courses
    ]

    return algolia_objects
