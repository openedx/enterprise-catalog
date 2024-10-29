import copy
import datetime
import logging
import time

from dateutil import parser
from django.core.cache import cache
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from pytz import UTC

from enterprise_catalog.apps.api_client.algolia import AlgoliaSearchClient
from enterprise_catalog.apps.api_client.constants import (
    COURSE_REVIEW_BASE_AVG_REVIEW_SCORE,
    COURSE_REVIEW_BAYESIAN_CONFIDENCE_NUMBER,
    DISCOVERY_AVERAGE_COURSE_REVIEW_CACHE_KEY,
)
from enterprise_catalog.apps.catalog.constants import (
    ALGOLIA_DEFAULT_TIMESTAMP,
    COURSE,
    EXEC_ED_2U_COURSE_TYPE,
    EXEC_ED_2U_READABLE_COURSE_TYPE,
    LATE_ENROLLMENT_THRESHOLD_DAYS,
    LEARNER_PATHWAY,
    PROGRAM,
    PROGRAM_TYPES_MAP,
    VIDEO,
)
from enterprise_catalog.apps.catalog.content_metadata_utils import (
    get_course_first_paid_enrollable_seat_price,
    get_course_run_by_uuid,
    is_course_run_active,
)
from enterprise_catalog.apps.catalog.models import ContentMetadata
from enterprise_catalog.apps.catalog.serializers import (
    NormalizedContentMetadataSerializer,
)
from enterprise_catalog.apps.catalog.utils import (
    batch_by_pk,
    localized_utcnow,
    to_timestamp,
)
from enterprise_catalog.apps.video_catalog.models import (
    Video,
    VideoSkill,
    VideoTranscriptSummary,
)


logger = logging.getLogger(__name__)

ALGOLIA_UUID_BATCH_SIZE = 100

ALGOLIA_JSON_METADATA_MAX_SIZE = 100000


# keep attributes from content objects that we explicitly want in Algolia
ALGOLIA_FIELDS = [
    'additional_information',
    'aggregation_key',
    'authoring_organizations',
    'availability',
    'card_image_url',  # for display on course cards
    'content_type',
    'course_keys',
    'enterprise_catalog_uuids',
    'enterprise_catalog_query_uuids',
    'enterprise_customer_uuids',
    'academy_uuids',
    'academy_tags',
    'video_ids',
    'transcript_summary',
    'video_usage_key',
    'video_skills',
    'course_run_key',
    'org',
    'logo_image_urls',
    'image_url',
    'duration',
    'full_description',
    'key',  # for links to Course about pages from the Learner Portal search page
    'uuid',
    'language',
    'level_type',
    'objectID',  # required by Algolia, e.g. "course-{uuid}"
    'outcome',
    'partner',
    'partners',
    'prerequisites',
    'prerequisites_raw',
    'programs',
    'program_titles',
    'program_type',
    'recent_enrollment_count',
    'short_description',
    'subjects',
    'skill_names',
    'skills',
    'subtitle',
    'title',
    'type',
    'advertised_course_run',  # a part of the advertised course run
    'course_runs',
    'upcoming_course_runs',
    'first_enrollable_paid_seat_price',
    'original_image_url',
    'marketing_url',
    'enterprise_catalog_query_titles',
    'learning_items',
    'prices',
    'course_details',
    'banner_image_url',
    'visible_via_association',
    'created',
    'course_type',
    'course_length',
    'entitlements',
    'learning_type',
    'learning_type_v2',
    'additional_metadata',
    # transformed metadata to consistent schema across all course
    # types (e.g., start date, end date, enroll by date).
    'normalized_metadata',
    'reviews_count',
    'avg_course_rating',
    'course_bayesian_average',
    'transcript_languages',
]

# default configuration for the index
ALGOLIA_INDEX_SETTINGS = {
    'attributeForDistinct': 'aggregation_key',
    'distinct': True,
    'typoTolerance': False,
    'searchableAttributes': [
        'unordered(title)',
        'unordered(full_description)',
        'unordered(short_description)',
        'unordered(additional_information)',
        'partners',
        'skill_names',
        'skills',
        'transcript_summary',
    ],
    'attributesForFaceting': [
        'availability',
        'content_type',
        'enterprise_catalog_uuids',
        'enterprise_catalog_query_uuids',
        'enterprise_customer_uuids',
        'academy_uuids',
        'searchable(academy_tags)',
        'language',
        'level_type',
        'program_type',
        'filterOnly(advertised_course_run.upgrade_deadline)',
        'searchable(partners.name)',
        'searchable(programs)',
        'searchable(program_titles)',
        'searchable(skill_names)',
        'searchable(skills)',
        'searchable(subjects)',
        'first_enrollable_paid_seat_price',
        'original_image_url',
        'marketing_url',
        'enterprise_catalog_query_titles',
        'course_type',
        'course_length',
        'aggregation_key',
        'learning_type',
        'learning_type_v2',
        'transcript_languages',
    ],
    'unretrievableAttributes': [
        'enterprise_catalog_uuids',
        'enterprise_customer_uuids',
        'academy_uuids',
    ],
    'customRanking': [
        'asc(visible_via_association)',
        'asc(created)',
        'desc(course_bayesian_average)',
        'desc(recent_enrollment_count)',
    ],
}


def _should_index_course(course_metadata):
    """
    Replicates the B2C index check of whether a certain course should be indexed for search.

    A course should only be indexed for algolia search if it has a non-indexed advertiseable course run, at least
    one owner, a marketing url slug, and the advertisable course run has a verified upgrade deadline in the future
    (in the case where there is *no* verified seat, or the upgrade deadline is null, we consider the deadline
    to be some arbitrarily distant date in the future).
    The course-discovery check that the course's partner is edX is included by default as the discovery API filters
    to the request's site's partner.
    The discovery check that the course has an availability level was decided to be a duplicate check that the
    website team plans on removing.
    Original code:
    https://github.com/openedx/course-discovery/blob/c6ac5329225e2f32cdf1d1da855d7c9d905b2576/course_discovery/apps/course_metadata/algolia_models.py#L218-L227

    Args:
        course (ContentMetadata): The ContentMetadata representing a course object.

    Returns:
        bool: Whether or not the course should be indexed by algolia.
    """
    course_json_metadata = course_metadata.json_metadata
    advertised_course_run_uuid = course_json_metadata.get('advertised_course_run_uuid')
    advertised_course_run = get_course_run_by_uuid(
        course_json_metadata,
        advertised_course_run_uuid,
    )

    # We define a series of no-arg functions, each of which has the property that,
    # if it returns true, means we should *not* index this record.
    def no_advertised_course_run_checker():
        return advertised_course_run is None

    def no_owners_checker():
        return len(course_json_metadata.get('owners') or []) < 1

    def run_is_hidden_checker():
        return bool(advertised_course_run.get('hidden'))

    def course_run_not_active_checker():
        return not is_course_run_active(advertised_course_run)

    def deadline_passed_checker():
        return _has_enroll_by_deadline_passed(course_json_metadata)

    for should_not_index_function, log_message in (
        (no_advertised_course_run_checker, 'no advertised course run'),
        (course_run_not_active_checker, 'no course run is active'),
        (deadline_passed_checker, 'enroll by deadline has passed'),
        (run_is_hidden_checker, 'advertised course run is hidden'),
        (no_owners_checker, 'no owners exist'),
    ):
        should_not_index = should_not_index_function()
        if should_not_index:
            logger.info(f'Not indexing {course_metadata.content_key}, reason: {log_message}')
            return False

    return True


def _has_enroll_by_deadline_passed(course_json_metadata):
    """
    Helper to determine if the enrollment deadline has passed for the given course
    based on normalized_metadata's enroll_by_date
    """
    enroll_by_deadline = course_json_metadata.get('normalized_metadata')['enroll_by_date']
    if isinstance(enroll_by_deadline, str):
        enroll_by_deadline_timestamp = parse_datetime(enroll_by_deadline).timestamp()
        return enroll_by_deadline_timestamp < localized_utcnow().timestamp()
    else:
        # Courses without enrollment deadline shouldn't be disqualified
        return False


def partition_course_keys_for_indexing(courses_content_metadata):
    """
    Returns both the indexable and non-indexable course content keys for Algolia.

    Args:
        courses_content_metadata (list of ContentMetadata): A list of ContentMetadata objects representing courses that
            should be filtered down.

    Returns:
        indexable_course_keys (list): Content key strings to be indexed
        nonindexable_course_keys (list): Content key strings to NOT be indexed
    """
    indexable_course_keys = set()
    nonindexable_course_keys = set()

    for course_metadata in courses_content_metadata:
        try:
            if _should_index_course(course_metadata):
                indexable_course_keys.add(course_metadata.content_key)
            else:
                nonindexable_course_keys.add(course_metadata.content_key)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning(
                f"Failed determining indexable status for course_metadata "
                f"'{course_metadata.content_key}' due to: {e}"
            )
    return list(indexable_course_keys), list(nonindexable_course_keys)


def _should_index_program(program_metadata):
    """
    Replicates the B2C index check of whether a certain program should be indexed for search.

    A program should only be indexed for algolia search if it has a marketing url,
    non-null program_type and availability_level, an active status and 'edX' as the partner.
    The course-discovery check that the course's partner is edX is included by default as the discovery API filters
    to the request's site's partner.
    The discovery check that the course has an availability level is a duplicate check that the website team
    plans on removing.
    Original code:
    https://github.com/openedx/course-discovery/blob/e0ece69ce8363eb765c524cd4eccb4b5cda35181/course_discovery/apps/course_metadata/algolia_models.py#L353

    Args:
        program (ContentMetadata): The ContentMetadata representing a program object.

    Returns:
        bool: Whether or not the program should be indexed by algolia.
    """
    program_json_metadata = program_metadata.json_metadata

    return program_json_metadata.get('marketing_url')\
        and program_json_metadata.get('type')\
        and not program_json_metadata.get('hidden')\
        and program_json_metadata.get('status') == 'active'


def partition_program_keys_for_indexing(programs_content_metadata):
    """
    Returns both the indexable and non-indexable program content keys for Algolia.

    Args:
        programs_content_metadata (list of ContentMetadata): A list of ContentMetadata objects representing programs
        that should be filtered down.

    Returns:
        indexable_program_keys (list): Content key strings to be indexed
        nonindexable_program_keys (list): Content key strings to NOT be indexed
    """
    indexable_program_keys = set()
    nonindexable_program_keys = set()

    for program_metadata in programs_content_metadata:
        if _should_index_program(program_metadata):
            indexable_program_keys.add(program_metadata.content_key)
        else:
            nonindexable_program_keys.add(program_metadata.content_key)

    return list(indexable_program_keys), list(nonindexable_program_keys)


def get_initialized_algolia_client():
    """
    Initializes and returns an Algolia client for updating search indices
    """
    algolia_client = AlgoliaSearchClient()
    algolia_client.init_index()
    return algolia_client


def configure_algolia_index(algolia_client):
    """
    Configures the settings for an Algolia index.
    """
    algolia_client.set_index_settings(ALGOLIA_INDEX_SETTINGS)


def get_algolia_object_id(content_type, uuid):
    """
    Given a uuid, returns an object_id to use for Algolia indexing.

    Arguments:
        uuid (str): a content uuid
        content_type(str): course or program

    Returns:
        str: the generated Algolia object_id or None if uuid is not specified
    """
    if uuid:
        return f'{content_type}-{uuid}'
    return None


def set_global_course_review_avg():
    """
    Retrieve all course reviews from the ContentMetadata records in the database, calculate the average review value
    and set the value to py-cache.
    """
    rolling_rating_sum = 0.0
    total_number_reviews = 0.0
    course_only_filter = Q(content_type='course')
    # only courses have course reviews
    for items_batch in batch_by_pk(ContentMetadata, batch_size=25, extra_filter=course_only_filter):
        for item in items_batch:
            if not item.json_metadata.get('avg_course_rating') or not item.json_metadata.get('reviews_count'):
                continue

            reviews_count = float(item.json_metadata.get('reviews_count'))
            avg_rating = float(item.json_metadata.get('avg_course_rating'))
            logger.info(
                f"set_global_course_review_avg found {reviews_count} course reviews for course: {item.content_key} "
                f"with avg score of {avg_rating}"
            )
            rolling_rating_sum += (avg_rating * reviews_count)
            total_number_reviews += reviews_count

    if rolling_rating_sum == 0 or total_number_reviews == 0:
        logger.warning("set_global_course_review_avg came up with no ratings, somehow.")
        return

    total_average_course_rating = rolling_rating_sum / total_number_reviews
    logger.info(f"set_global_course_review_avg saving average course rating value: {total_average_course_rating}")
    cache.set(
        DISCOVERY_AVERAGE_COURSE_REVIEW_CACHE_KEY,
        total_average_course_rating,
    )


def get_global_course_review_avg():
    """
    Fetch the calculated global course review average from py-cache
    """
    cache_key = DISCOVERY_AVERAGE_COURSE_REVIEW_CACHE_KEY
    return cache.get(cache_key, COURSE_REVIEW_BASE_AVG_REVIEW_SCORE)


def get_course_bayesian_average(course):
    """
    Using the global average review value to calculate an individual course's bayesian average review value.
    https://www.algolia.com/doc/guides/managing-results/must-do/custom-ranking/how-to/bayesian-average/
    """
    if course.get('avg_course_rating') is None:
        return 0

    if course.get('reviews_count') is None:
        return 0

    total_avg = float(get_global_course_review_avg())
    avg_review = float(course.get('avg_course_rating'))
    ratings_count = float(course.get('reviews_count'))
    return (
        (avg_review * ratings_count) + (total_avg * COURSE_REVIEW_BAYESIAN_CONFIDENCE_NUMBER)
    ) / (ratings_count + COURSE_REVIEW_BAYESIAN_CONFIDENCE_NUMBER)


def get_course_language(course):
    """
    Gets the human-readable language name associated with the advertised course run. Used for
    the "Language" facet in Algolia.

    Arguments:
        course (dict): a dict representing with course metadata

    Returns:
        string: human-readable language name parsed from a language code, or None if language name is not present.
    """
    advertised_course_run = get_course_run_by_uuid(course, course.get('advertised_course_run_uuid'))
    if not advertised_course_run:
        return None

    content_language_name = advertised_course_run.get('content_language_search_facet_name')
    return content_language_name


def get_course_transcript_languages(course):
    """
    Gets the human-readable video transcript languages associated with the advertised course run. Used for
    the "transcript_languages" facet in Algolia.

    Arguments:
        course (dict): a dict representing with course metadata

    Returns:
        list: a list of available human-readable video transcript languages parsed from a language code.
    """
    advertised_course_run = get_course_run_by_uuid(course, course.get('advertised_course_run_uuid'))
    if not advertised_course_run:
        return None

    transcript_languages = advertised_course_run.get('transcript_languages_search_facet_names')
    return transcript_languages


def get_course_availability(course):
    """
    Gets the availability for a course. Used for the "Availability" facet in Algolia.

    Arguments:
        course (dict): a dict representing with course metadata

    Returns:
        list: a list of availabilities for those course runs (e.g., "Upcoming")
    """
    DEFAULT_COURSE_AVAILABILITY = 'Archived'
    COURSE_AVAILABILITY_MESSAGES = {
        'current': 'Available Now',
        'upcoming': 'Upcoming',
        'starting soon': 'Starting Soon',
    }
    course_runs = course.get('course_runs') or []
    active_course_runs = [run for run in course_runs if is_course_run_active(run)]
    availability = set()
    for course_run in active_course_runs:
        run_availability = course_run.get('availability') or ''
        availability.add(
            COURSE_AVAILABILITY_MESSAGES.get(run_availability.lower(), DEFAULT_COURSE_AVAILABILITY)
        )
    return list(availability)


def is_course_archived(course):
    """
    Determines if the availability for a course is "Archived"

    Arguments:
        course (dict): a dict representing with course metadata

    Returns:
        boolean: "Archived" availability or not
    """
    availability_list = get_course_availability(course)
    return len(availability_list) == 0 or 'Archived' in availability_list


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
    org_name_override = course.get('organization_short_code_override')
    logo_override = course.get('organization_logo_override_url')

    for owner in owners:
        partner_name = owner.get('name')
        if partner_name:
            partner_metadata = {
                'name': org_name_override or partner_name,
                'logo_image_url': logo_override or owner.get('logo_image_url'),
            }
            partners.append(partner_metadata)

    return partners


def _get_course_program_field(course, field):
    """
    Helper to pluck a list of values for the given field out of a course's programs.

    Arguments:
        course (dict): a dictionary representing a course
        field (str): the name of a field to return values of.
    Returns:
        list: a list of the values for a certain field in a program associated with the course.
    """
    programs = course.get('programs') or []
    return list({
        value for program in programs
        if (value := program.get(field))
    })


def get_program_course_details(program):
    """
    Returns courses for a program, with just enough detail to use in frontend clients (for now)
    """
    courses = program.get('courses') or []
    course_list = []
    for course in courses:
        mapped_course = {
            'key': course.get('key'),
            'title': course.get('title'),
            'image': course.get('image').get('src') if course.get('image') else None,
            'short_description': course.get('short_description'),
        }
        course_list.append(mapped_course)
    return course_list


def get_pathway_course_keys(pathway):
    """
    Gets list of course keys associated with the pathway.

    Arguments:
       pathway (dict): a dictionary representing a pathway.

    Returns:
       list: a list of course keys associated with the pathway.
    """
    course_keys = set()
    steps = pathway.get('steps') or []
    for step in steps:
        courses = step.get('courses') or []
        for course in courses:
            course_keys.add(course['key'])
    return list(course_keys)


def get_pathway_program_uuids(pathway):
    """
    Gets list of program uuids associated with the pathway.

    Arguments:
       pathway (dict): a dictionary representing a pathway.

    Returns:
       list: a list of program uuids associated with the pathway.
    """
    program_uuids = set()
    steps = pathway.get('steps') or []
    for step in steps:
        programs = step.get('programs') or []
        for program in programs:
            program_uuids.add(program['uuid'])
    return list(program_uuids)


def get_pathway_availability(pathway):
    """
    Gets the availability for a pathway. Used for the "availability" facet in Algolia.

    Arguments:
        pathway (dict): a dictionary representing a pathway.

    Returns:
        list: a union of pathway programs and courses availability.
    """
    availability = set()
    pathway_course_keys = get_pathway_course_keys(pathway)
    courses_metadata = ContentMetadata.objects.filter(content_key__in=pathway_course_keys)
    for course_metadata in courses_metadata:
        course_status = get_course_availability(course_metadata.json_metadata)
        availability.update(course_status)
    pathway_program_uuids = get_pathway_program_uuids(pathway)
    programs_metadata = ContentMetadata.objects.filter(content_key__in=pathway_program_uuids)
    for program_metadata in programs_metadata:
        program_status = get_program_availability(program_metadata.json_metadata)
        availability.update(program_status)
    return list(availability)


def get_pathway_card_image_url(pathway):
    """
    Gets the card_image

    Arguments:
        pathway (dict): a dictionary representing a pathway.

    Returns:
        str: url to card size image
    """
    images = pathway.get('card_image', {})
    try:
        return images.get('card').get('url')
    except (KeyError, AttributeError):
        return None


def get_pathway_partners(pathway):
    """
    Gets the partners for a pathway. Used for the "partners.name" facet in Algolia.

    Arguments:
        pathway (dict): a dictionary representing a pathway.

    Returns:
        list: a list of partners associated with the pathway.
    """
    partners = []
    pathway_course_keys = get_pathway_course_keys(pathway)
    courses_metadata = ContentMetadata.objects.filter(content_key__in=pathway_course_keys)
    for course in courses_metadata:
        course_partners = get_course_partners(course.json_metadata)
        for partner in course_partners:
            partner_name = partner.get('name')
            if partner_name not in [item.get('name') for item in partners]:
                partners.append(partner)
    pathway_program_uuids = get_pathway_program_uuids(pathway)
    programs_metadata = ContentMetadata.objects.filter(content_key__in=pathway_program_uuids)
    for program in programs_metadata:
        program_partners = get_program_partners(program.json_metadata)
        for partner in program_partners:
            partner_name = partner.get('name')
            if partner_name not in [item.get('name') for item in partners]:
                partners.append(partner)
    return partners


def get_pathway_subjects(pathway):
    """
    Gets the subjects for a pathway. Used for the "subjects" facet in Algolia.

    Arguments:
        pathway (dict): a dictionary representing a pathway.

    Returns:
        list: a list of subjects associated with the pathway.
    """
    subjects = set()
    pathway_course_keys = get_pathway_course_keys(pathway)
    courses_metadata = ContentMetadata.objects.filter(content_key__in=pathway_course_keys)
    for course in courses_metadata:
        course_subjects = get_course_subjects(course.json_metadata)
        subjects.update(course_subjects)
    pathway_program_uuids = get_pathway_program_uuids(pathway)
    programs_metadata = ContentMetadata.objects.filter(content_key__in=pathway_program_uuids)
    for program in programs_metadata:
        program_subjects = get_program_subjects(program.json_metadata)
        subjects.update(program_subjects)
    return list(subjects)


def get_pathway_created_date(pathway):
    """
    Gets the created date for a pathway. Used for the sorting pathways based on created date in Algolia.

    Arguments:
        pathway (dict): a dictionary representing a pathway.

    Returns:
        str: Pathway created date as Unix timestamp or default date that lies way ahead in the future.
    """
    created = pathway.get('created')
    if created:
        created_datetime = parse_datetime(created)
        return time.mktime(created_datetime.timetuple())
    return None


def _get_program_course_field(program, field):
    """
    Helper to pluck a list of values for the given field out of a program's courses.

    Arguments:
        program (dict): a dictionary representing a program
        field (str): the name of a field to return values of.
    Returns:
        list: a list of the values for a certain field in a course associated with the program.
    """
    courses = program.get('courses') or []
    return list({
        value for course in courses
        if (value := course.get(field))
    })


def get_program_course_keys(program):
    """
    Gets list of course keys associated with the program.

    Arguments:
       program (dict): a dictionary representing a program.

    Returns:
       list: a list of course keys associated with the program.
    """
    return _get_program_course_field(program, 'key')


def get_program_type(program):
    """
    Gets the program_type for a program. Used for the "program_type" facet in Algolia.

    Arguments:
        program (dict): a dictionary representing a program.

    Returns:
        str: program_type e.g: MicroMasters® Program
    """
    program_type = program.get('type')
    return PROGRAM_TYPES_MAP.get(program_type)


def get_program_title(program):
    """
    Gets the title for a program.

    Arguments:
        program (dict): a dictionary representing a program.

    Returns:
        str: program_title e.g: Data Engineering Fundamentals
    """
    return program.get('title')


def get_program_availability(program):
    """
    Gets the availability for a program. Used for the "availability" facet in Algolia.

    Arguments:
        program (dict): a dictionary representing a program.

    Returns:
        list: a union of program courses availability.
    """
    # Master's programs don't have courses in the same way that our other programs do.
    program_type = program.get('type')
    if program_type and program_type == 'Masters':
        return [_('Available now')]

    availability = set()
    for course in program.get('courses', []):
        course_status = get_course_availability(course)
        for status in course_status:
            availability.add(status)
    return list(availability)


def get_program_partners(program):
    """
    Gets the partners for a program. Used for the "partners.name" facet in Algolia.

    Arguments:
        program (dict): a dictionary representing a program.

    Returns:
        list: a list of partners associated with the program.
    """
    partners = []
    for course in program.get('courses', []):
        course_partners = get_course_partners(course)
        for partner in course_partners:
            partner_name = partner.get('name')
            if partner_name not in [item.get('name') for item in partners]:
                partners.append(partner)
    return partners


def get_program_subjects(program):
    """
    Gets the subjects for a program. Used for the "subjects" facet in Algolia.

    Arguments:
        program (dict): a dictionary representing a program.

    Returns:
        list: a list of subjects associated with the program.
    """
    subjects = set()
    for course in program.get('courses', []):
        course_metadata = ContentMetadata.objects.filter(content_key=course.get('key')).first()
        if course_metadata:
            course_subjects = get_course_subjects(course_metadata.json_metadata)
            subjects.update(course_subjects)
    return list(subjects)


def get_program_skill_names(program):
    """
    Gets the skills for a program. Used for the "skill_names" facet in Algolia.

    Arguments:
        program (dict): a dictionary representing a program.

    Returns:
        list: a list of skill_names associated with the program.
    """
    skill_names = set()
    for course in program.get('courses', []):
        course_metadata = ContentMetadata.objects.filter(content_key=course.get('key')).first()
        if course_metadata:
            course_skills = get_course_skill_names(course_metadata.json_metadata)
            skill_names.update(course_skills)
    return list(skill_names)


def get_program_level_type(program):
    """
    Gets the level_type for a program. Used for the "level_type" facet in Algolia.

    Arguments:
        program (dict): a dictionary representing a program.

    Returns:
        str: level type associated with the program.
    """
    level_types = []
    for course in program.get('courses', []):
        course_metadata = ContentMetadata.objects.filter(content_key=course.get('key')).first()
        if course_metadata:
            course_level_type = course_metadata.json_metadata.get('level_type')
            if course_level_type:
                level_types.append(course_level_type)
    return max(set(level_types), key=level_types.count) if level_types else ''


def get_program_learning_items(program):
    """
    Gets the expected_learning_items for a program. Used for the "learning_items" facet in Algolia.

    Arguments:
        program (dict): a dictionary representing a program.

    Returns:
        list(str): list of learning items.
    """
    return program.get('expected_learning_items', [])


def get_program_prices(program):
    """
    Gets the prices (only USD for now) for a program. Used for the "prices" facet in Algolia.

    Arguments:
        program (dict): a dictionary representing a program.

    Returns:
        array of price dict values: e.g., [{'currency': 'USD', 'total': 169}]
    """
    price_ranges = program.get('price_ranges', [])
    if not price_ranges:
        return []
    prices = [price for price in price_ranges if price.get('currency', '') == 'USD']
    return prices


def get_program_banner_image_url(program):
    """
    Gets the banner_image_url (only large is fetched), rest of urls can be deduced

    Arguments:
        program (dict): a dictionary representing a program.

    Returns:
        str: url to large size image
    """
    images = program.get('banner_image', {})
    try:
        return images.get('large').get('url')
    except (KeyError, AttributeError):
        return None


def get_course_program_types(course):
    """
    Gets list of program types associated with the course. Used for the "Programs"
    facet in Algolia.

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        list: a list of program types associated with the course
    """
    return _get_course_program_field(course, 'type')


def get_course_program_titles(course):
    """
    Gets list of program titles associated with the course. Used for the "Program titles"
    facet in Algolia.

    Arguments:
        course (dict): a dictionary representing a course.

    Returns:
        list: a list of program titles associated with the course.
    """
    return _get_course_program_field(course, 'title')


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


def get_course_marketing_url(course):
    """
    Gets the appropriate marketing url to direct users to the course details page.

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        str: the url for the B2C course details page
    """
    marketing_url = course.get('marketing_url')
    return marketing_url


def get_course_original_image_url(course):
    """
    Gets the appropriate original image to use for displaying course metadata.

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        str: the url for the course original image
    """
    # Account for the small chance that the original image will be None
    original_image_url = course.get('original_image')
    if original_image_url:
        original_image_url = original_image_url.get('src')
    return original_image_url


def get_course_card_image_url(course):
    """
    Gets the appropriate image to use for course cards.

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        str: the url for the course card image
    """
    image_url = course.get('image_url')
    return image_url


def get_course_skill_names(course):
    """
    Gets the skill names associated with a course.

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        list: a list of skill names associated with the course
    """
    skill_names = course.get('skill_names') or []
    return list(set(skill_names))


def get_course_skills(course):
    """
    Gets the skills associated with a course.

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        skills (list): list of dictionaries containing skill name, description
    """
    skills = course.get('skills') or []
    return list(skills)


def get_course_outcome(course):
    """
    Gets the course outcome description, no tags.

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        str: the course outcome stripped of tags
    """
    outcome = course.get('outcome')
    return outcome


def get_course_prerequisites(course):
    """
    Gets the course prerequisites description, no tags.

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        str: the course prerequisites stripped of tags
    """
    prerequisites = course.get('prerequisites_raw')
    return prerequisites


def _get_course_run(course, course_run):
    """
    Transform a course run into what gets indexed in Algolia. Depending on the course type,
    some metadata may be derived from the top-level course (e.g., for Exec Ed vs. OCM content).

    Date attributes (e.g., `enroll_by`) are recorded as Unix timestamps so Algolia can filter on them.

    Arguments:
        course (dict): a dictionary representing a course
        course_run (dict): a dictionary representing a course run

    Returns:
        dict: a subseted and transformed dictionary from course_run
    """
    if course is None or course_run is None:
        return None

    normalized_content_metadata = NormalizedContentMetadataSerializer({
        'course_metadata': course,
        'course_run_metadata': course_run,
    }).data

    enroll_by = _get_course_run_enroll_by_date_timestamp(normalized_content_metadata)
    enroll_start = _get_course_run_enroll_start_date_timestamp(normalized_content_metadata)

    course_run = {
        'key': course_run.get('key'),
        'pacing_type': course_run.get('pacing_type'),
        'availability': course_run.get('availability'),
        'start': course_run.get('start'),
        'end': course_run.get('end'),
        'min_effort': course_run.get('min_effort'),
        'max_effort': course_run.get('max_effort'),
        'weeks_to_complete': course_run.get('weeks_to_complete'),
        'upgrade_deadline': _get_verified_upgrade_deadline(course_run),  # deprecated in favor of `enroll_by`
        'enroll_by': enroll_by,
        'has_enroll_by': bool(enroll_by),
        'enroll_start': enroll_start,
        'has_enroll_start': bool(enroll_start),
        'content_price': normalized_content_metadata.get('content_price'),
        'is_active': _get_is_active_course_run(course_run),
        'is_late_enrollment_eligible': _get_is_late_enrollment_eligible(course_run),
        'restriction_type': course_run.get('restriction_type'),
    }
    return course_run


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
    return _get_course_run(course, full_course_run)


def get_course_runs(course):
    """
    Extract and transform a list of course runs into what we'll index.

    Arguments:
        course (dict): a dictionary representing a course

    Returns:
        list(dict): a list of subseted and transformed course_runs
    """
    output = []
    course_runs = course.get('course_runs') or []
    for course_run in course_runs:
        this_course_run = _get_course_run(course, course_run)
        has_ended = False
        is_eligible_for_enrollment = True
        if enroll_by := this_course_run.get('enroll_by'):
            # determine whether the course run is late enrollment eligible, based on an
            # enroll_by date that has elapsed the earliest support late enrollment cutoff.
            course_run_enroll_by_date = datetime.datetime.fromtimestamp(enroll_by).replace(tzinfo=UTC)
            if course_run_enroll_by_date < localized_utcnow():
                # the enroll_by date has passed, so determine whether the enroll_by
                # is still eligible for late enrollment.
                late_enrollment_cutoff = localized_utcnow() - datetime.timedelta(days=LATE_ENROLLMENT_THRESHOLD_DAYS)
                is_eligible_for_enrollment = course_run_enroll_by_date > late_enrollment_cutoff
        if end := this_course_run.get('end'):
            course_run_end = parser.parse(end)
            # check for runs within course run end date
            has_ended = course_run_end < localized_utcnow()
        if has_ended or not is_eligible_for_enrollment:
            # skip course runs which have ended or are not eligible for enrollment, taking into account late enrollment.
            continue
        output.append(this_course_run)
    return output


def get_upcoming_course_runs(course):
    """
    Get number of upcoming course runs.

    Argument:
        course (dict)

    Returns:
        int: the number of course runs in the future
    """
    course_runs = course.get('course_runs') or []
    active_course_runs = [run for run in course_runs if is_course_run_active(run)]
    if get_advertised_course_run(course) is not None:
        return len(active_course_runs) - 1
    return len(active_course_runs)


def _get_verified_upgrade_deadline(full_course_run):
    """
    Check to see if course has a verified seat option, and if so, return the verified upgrade deadline

    Arguments:
        full_course_run (dict): a course_run or None

    Returns:
        str: Verified Upgrade Deadline (VUD) as Unix timestamp or default large expiration date
    """
    seats = full_course_run.get('seats') or []
    for seat in seats:
        if seat.get('type') == 'verified' and 'upgrade_deadline' in seat and seat.get('upgrade_deadline') is not None:
            vud_datetime = parse_datetime(seat.get('upgrade_deadline'))
            return time.mktime(vud_datetime.timetuple())
    # defaults to year 3000, as algolia cannot filter on null values
    return ALGOLIA_DEFAULT_TIMESTAMP


def _get_is_active_course_run(full_course_run):
    """
    Determines if the course run meets the criteria of:
    is_marketable: true
    is_enrollable: true
    availability: 'Current' || 'Upcoming' || 'Starting Soon'
    is_published: 'published'

    It resolves the logic into an indexed field on the course run labeled 'is_active'
    """
    course_run_is_active = is_course_run_active(full_course_run)
    availability = full_course_run.get('availability')
    is_not_archived_availability = availability != 'Archived'
    is_active = course_run_is_active and is_not_archived_availability
    if not is_active:
        logger.info(
            f'[_get_is_active_course_run] course run is not active '
            f'key: {full_course_run.get("key")}, '
            f'is_marketable: {full_course_run.get("is_marketable")}, '
            f'is_enrollable: {full_course_run.get("is_enrollable")}, '
            f'availability: {availability}, '
            f'status: {full_course_run.get("status")}'
        )
    return is_active


def _get_is_late_enrollment_eligible(course_run):
    """
    Determines if the course run is eligible for late enrollment:
      * Must not be archived
      * Must have a marketing URL
      * Must have seats
    """
    is_archived = course_run.get('availability') == 'Archived'
    has_marketing_url = bool(course_run.get('marketing_url'))
    has_seats = bool(course_run.get('seats'))
    if is_archived or not has_marketing_url or not has_seats:
        return False
    return True


def _get_course_run_enroll_by_date_timestamp(normalized_content_metadata):
    """
    Returns a transformed enroll-by date, converted to a Unix timestamp.

    If no enroll-by date is provided, it returns None.
    """
    enroll_by_date = normalized_content_metadata.get('enroll_by_date')
    if not enroll_by_date:
        return None
    return to_timestamp(enroll_by_date)


def _get_course_run_enroll_start_date_timestamp(normalized_content_metadata):
    """
    Returns a transformed enrollment start date, converted to a Unix timestamp.

    If no enrollment_start date is provided, it returns None.
    """
    enroll_start_date = normalized_content_metadata.get('enroll_start_date')
    if not enroll_start_date:
        return None
    return to_timestamp(enroll_start_date)


def get_learning_type(content):
    """
    Gets the content's learning type, checking and returning if the content
    is of course type exec ed. Othwise returning the `content_type` field value

    Arguments:
        course (dict): a dictionary representing a piece of content

    Returns:
        str: the learning type (ADR: docs/decisions/0005-creating-learning-type-facet)
        of the course.
    """
    if content.get('course_type') == EXEC_ED_2U_COURSE_TYPE:
        return EXEC_ED_2U_READABLE_COURSE_TYPE
    return content.get('content_type')


def get_learning_type_v2(content):
    """
    Placeholder learning type value used while switching exec ed learning type
    to a readable value
    """
    if content.get('course_type') == EXEC_ED_2U_COURSE_TYPE:
        return EXEC_ED_2U_READABLE_COURSE_TYPE
    return content.get('content_type')


def get_reviews_count(content):
    """
    Gets the content's reviews count

    Arguments:
        course (dict): a dictionary representing a piece of content

    Returns:
        int: the reviews count of the course.
    """
    return content.get('reviews_count')


def get_avg_course_rating(content):
    """
    Gets the content's average course rating

    Arguments:
        course (dict): a dictionary representing a piece of content

    Returns:
        float: the average course rating of the course.
    """
    return content.get('avg_course_rating')


def get_video_partners(video):
    """
    Gets list of partners associated with the video. Used for the "Partners" facet and
    searchable attribute in Algolia.

    Arguments:
        video (obj): the video model object

    Returns:
        list: a list of partner metadata associated with the course
    """
    course_content_key = video.parent_content_metadata.parent_content_key
    try:
        course_metadata = ContentMetadata.objects.get(content_key=course_content_key)
        return get_course_partners(course_metadata.json_metadata) if course_metadata else []
    except ContentMetadata.DoesNotExist:
        return []


def get_transcript_summary(video):
    """
    Gets transcript summary of the video

    Arguments:
        video (obj): the video model object

    Returns:
        str: video transcript summary
    """
    transcript_summary = VideoTranscriptSummary.objects.filter(video=video).first()
    return transcript_summary.summary if transcript_summary else ''


def get_video_skills(video):
    """
    Gets skills associated with the video

    Arguments:
        video (obj): the video model object

    Returns:
        list: a list of skills associated with the video
    """
    video_skills = VideoSkill.objects.filter(video=video).values_list('name', flat=True)
    return list(video_skills) if video_skills else []


def get_video_course_run_key(video):
    """
    Gets course run key associated with the video

    Arguments:
        video (obj): the video model object

    Returns:
        str: course run key
    """
    video_parent_cm = video.parent_content_metadata
    return video_parent_cm.json_metadata.get('key') if video_parent_cm else ''


def get_video_org(video):
    """
    Gets organization associated with the video

    Arguments:
        video (obj): the video model object

    Returns:
        str: organization code
    """
    video_parent_cm = video.parent_content_metadata
    return video_parent_cm.json_metadata.get('org') if video_parent_cm else ''


def get_video_logo_image_urls(video):
    """
    Gets logo image urls associated with the video

    Arguments:
        video (obj): the video model object

    Returns:
        list: a list of logo image urls associated with the video
    """
    video_parent_cm = video.parent_content_metadata
    return list(video_parent_cm.json_metadata.get('logo_image_urls', [])) if video_parent_cm else []


def get_video_image_url(video):
    """
    Gets image url associated with the video

    Arguments:
        video (obj): the video model object

    Returns:
        str: video image url
    """
    video_parent_cm = video.parent_content_metadata
    return video_parent_cm.json_metadata.get('image_url') if video_parent_cm else ''


def get_video_duration(video):
    """
    Gets video duration associated with the video

    Arguments:
        video (obj): the video model object

    Returns:
        str: video duration
    """
    return video.json_metadata.get('duration')


def _first_enrollable_paid_seat_price(course_record):
    """
    Returns the course-level first_enrollable_paid_seat_price,
    or computes it based on the course runs.
    """
    if course_value := course_record.get('first_enrollable_paid_seat_price'):
        return course_value
    return get_course_first_paid_enrollable_seat_price(course_record)


def _algolia_object_from_product(product, algolia_fields):
    """
    Transforms a course or program into an Algolia object.

    Arguments:
        product (dict): a course or program dict
        algolia_fields (list): list of fields to extract from the course or program

    Returns:
        dict: a dictionary containing only the fields noted in algolia_fields
    """
    searchable_product = copy.deepcopy(product)
    if searchable_product.get('content_type') == COURSE:
        searchable_product.update({
            'language': get_course_language(searchable_product),
            'availability': get_course_availability(searchable_product),
            'partners': get_course_partners(searchable_product),
            'programs': get_course_program_types(searchable_product),
            'program_titles': get_course_program_titles(searchable_product),
            'subjects': get_course_subjects(searchable_product),
            'card_image_url': get_course_card_image_url(searchable_product),
            'advertised_course_run': get_advertised_course_run(searchable_product),
            'course_runs': get_course_runs(searchable_product),
            'upcoming_course_runs': get_upcoming_course_runs(searchable_product),
            'skill_names': get_course_skill_names(searchable_product),
            'skills': get_course_skills(searchable_product),
            'first_enrollable_paid_seat_price': _first_enrollable_paid_seat_price(searchable_product),
            'original_image_url': get_course_original_image_url(searchable_product),
            'marketing_url': get_course_marketing_url(searchable_product),
            'outcome': get_course_outcome(searchable_product),
            'prerequisites': get_course_prerequisites(searchable_product),
            'learning_type': get_learning_type(searchable_product),
            'learning_type_v2': get_learning_type_v2(searchable_product),
            'reviews_count': get_reviews_count(searchable_product),
            'avg_course_rating': get_avg_course_rating(searchable_product),
            'course_bayesian_average': get_course_bayesian_average(searchable_product),
            'transcript_languages': get_course_transcript_languages(searchable_product),
        })
    elif searchable_product.get('content_type') == PROGRAM:
        searchable_product.update({
            'course_keys': get_program_course_keys(searchable_product),
            'programs': [get_program_type(searchable_product)],
            'program_titles': [get_program_title(searchable_product)],
            'program_type': get_program_type(searchable_product),
            'availability': get_program_availability(searchable_product),
            'partners': get_program_partners(searchable_product),
            'subjects': get_program_subjects(searchable_product),
            'skill_names': get_program_skill_names(searchable_product),
            'level_type': get_program_level_type(searchable_product),
            'learning_items': get_program_learning_items(searchable_product),
            'prices': get_program_prices(searchable_product),
            'banner_image_url': get_program_banner_image_url(searchable_product),
            'course_details': get_program_course_details(searchable_product),
            'learning_type': get_learning_type(searchable_product),
            'learning_type_v2': get_learning_type_v2(searchable_product),
        })
    elif searchable_product.get('content_type') == LEARNER_PATHWAY:
        searchable_product.update({
            'course_keys': get_pathway_course_keys(searchable_product),
            'programs': get_pathway_program_uuids(searchable_product),
            'availability': get_pathway_availability(searchable_product),
            'card_image_url': get_pathway_card_image_url(searchable_product),
            'partners': get_pathway_partners(searchable_product),
            'subjects': get_pathway_subjects(searchable_product),
            'created': get_pathway_created_date(searchable_product),
            'learning_type': get_learning_type(searchable_product),
            'learning_type_v2': get_learning_type_v2(searchable_product),
        })
    elif searchable_product.get('content_type') == VIDEO:
        try:
            edx_video_id = searchable_product.get('aggregation_key')
            video = Video.objects.get(edx_video_id=edx_video_id)
            searchable_product.update({
                'partners': get_video_partners(video),
                'transcript_summary': get_transcript_summary(video),
                'video_skills': get_video_skills(video),
                'course_run_key': get_video_course_run_key(video),
                'org': get_video_org(video),
                'logo_image_urls': get_video_logo_image_urls(video),
                'image_url': get_video_image_url(video),
                'duration': get_video_duration(video),
            })
        except Video.DoesNotExist:
            logger.warning(f"video not found for aggregation_key: {edx_video_id}")

    algolia_object = {}
    keys = searchable_product.keys()
    for field in algolia_fields:
        if field in keys:
            field_value = searchable_product.get(field)
            if field_value is not None:
                algolia_object[field] = field_value

    return algolia_object


def create_algolia_objects(products, algolia_fields):
    """
    Transforms content into Algolia objects.

    Arguments:
        products (list): list of courses or programs
        algolia_fields (list): list of fields to extract from courses and programs

    Returns:
        list: a list of Algolia objects containing only the fields noted in algolia_fields
    """
    if not algolia_fields:
        algolia_fields = []

    algolia_objects = [
        _algolia_object_from_product(product, algolia_fields)
        for product in products
    ]

    return algolia_objects
