import datetime
import logging
import math

from dateutil import parser
from django.utils.html import strip_tags

from enterprise_catalog.apps.catalog.algolia_utils import ALGOLIA_INDEX_SETTINGS


logger = logging.getLogger(__name__)


CSV_COURSE_HEADERS = [
    'Title',
    'Partner Name',
    'Start',
    'End',
    'Verified Upgrade Deadline',
    'Program Type',
    'Program Name',
    'Pacing',
    'Level',
    'Price',
    'Language',
    'Subtitles',
    'URL',
    'Short Description',
    'Subjects',
    'Key',
    'Short Key',
    'Skills',
    'Min Effort',
    'Max Effort',
    'Length',
    'What You’ll Learn',
    'Pre-requisites',
    'Associated Catalogs',
]

CSV_PROGRAM_HEADERS = [
    'Title',
    'Program Type',
    'Partner',
    'Short Description',
    'Number of courses',
    'Associated Catalogs',
]

CSV_COURSE_RUN_HEADERS = [
    'Title',
    'Key',
    'Course Short Key',
    'Pacing',
    'Availability',
    'Start Date',
    'End Date',
    'Verified Upgrade Deadline',
    'Min Effort',
    'Max Effort',
    'Length',
    'Programs',
    'Program Type',
    'Skills',
    'Subjects',
    'Language',
    'Subtitles',
    'Associated Catalogs'
]

CSV_EXEC_ED_COURSE_HEADERS = [
    'Title',
    'Partner Name',
    'Start',
    'End',
    'Registration Deadline',
    'Price',
    'Language',
    'Subtitles',
    'URL',
    'Short Description',
    'Subjects',
    'Key',
    'Short Key',
    'Skills',
    'Min Effort',
    'Max Effort',
    'Length',
    'What You’ll Learn',
    'Full Description',
]

ALGOLIA_ATTRIBUTES_TO_RETRIEVE = [
    'additional_metadata',
    'advertised_course_run',
    'aggregation_key',
    'content_type',
    'course_keys',
    'course_runs',
    'course_type',
    'entitlements',
    'enterprise_catalog_query_titles',
    'first_enrollable_paid_seat_price',
    'full_description',
    'key',
    'language',
    'transcript_languages',
    'level_type',
    'marketing_url',
    'outcome',
    'partners',
    'prerequisites_raw',
    'program_titles',
    'program_type',
    'programs',
    'short_description',
    'skills',
    'subjects',
    'subtitle',
    'title',
]

DATE_FORMAT = "%Y-%m-%d"


def write_headers_to_sheet(worksheet, headers, cell_format):
    """
    Helper function to write a given list of strings as a header row in a given worksheet.
    """
    for col_num, cell_data in enumerate(headers):
        worksheet.set_column(0, col_num, 30)
        worksheet.write(0, col_num, cell_data, cell_format)


def fetch_catalog_types(hit):
    """
    Helper function to extract only the three needed catalog types.
    """
    CATALOG_TYPES = [
        'A la carte',
        'Business',
        'Education',
        'Subscription'
    ]

    return [catalog for catalog in CATALOG_TYPES if catalog in hit.get('enterprise_catalog_query_titles')]


def program_hit_to_row(hit):
    """
    Helper function to construct a CSV row according to a single Algolia result program hit.
    """
    csv_row = []
    csv_row.append(hit.get('title'))
    csv_row.append(hit.get('program_type'))

    partners = [partner['name'] for partner in hit.get('partners', [])]
    csv_row.append(', '.join(partners))

    csv_row.append(hit.get('subtitle'))

    csv_row.append(len(hit.get('course_keys', [])))

    catalogs = fetch_catalog_types(hit)
    csv_row.append(', '.join(catalogs))

    return csv_row


# pylint: disable=too-many-statements
def course_hit_to_row(hit):
    """
    Helper function to construct a CSV row according to a single Algolia result course hit.
    """
    csv_row = []
    csv_row.append(hit.get('title'))

    if hit.get('partners'):
        csv_row.append(hit['partners'][0]['name'])
    else:
        csv_row.append(None)

    if hit.get('advertised_course_run'):
        start_date = None
        if hit['advertised_course_run'].get('start'):
            start_date = parser.parse(hit['advertised_course_run']['start']).strftime(DATE_FORMAT)
        csv_row.append(start_date)

        end_date = None
        if hit['advertised_course_run'].get('end'):
            end_date = parser.parse(hit['advertised_course_run']['end']).strftime(DATE_FORMAT)
        csv_row.append(end_date)

        upgrade_deadline = None
        if hit['advertised_course_run'].get('upgrade_deadline'):
            raw_deadline = hit['advertised_course_run']['upgrade_deadline']
            upgrade_deadline = datetime.datetime.fromtimestamp(raw_deadline).strftime(DATE_FORMAT)
        csv_row.append(upgrade_deadline)

        pacing_type = hit['advertised_course_run']['pacing_type']
        key = hit['advertised_course_run'].get('key')
    else:
        csv_row.append(None)  # no start date
        csv_row.append(None)  # no end date
        csv_row.append(None)  # no upgrade deadline
        pacing_type = None
        key = None

    csv_row.append(', '.join(hit.get('programs', [])))
    csv_row.append(', '.join(hit.get('program_titles', [])))

    csv_row.append(pacing_type)

    csv_row.append(hit.get('level_type'))

    csv_row.append(hit.get('first_enrollable_paid_seat_price'))
    csv_row.append(hit.get('language'))
    csv_row.append(', '.join(hit.get('transcript_languages', [])))
    csv_row.append(hit.get('marketing_url'))
    csv_row.append(strip_tags(hit.get('short_description', '')))

    csv_row.append(', '.join(hit.get('subjects', [])))
    csv_row.append(key)
    csv_row.append(hit.get('aggregation_key'))

    skills = [skill['name'] for skill in hit.get('skills', [])]
    csv_row.append(', '.join(skills))

    advertised_course_run = hit.get('advertised_course_run', {})
    csv_row.append(advertised_course_run.get('min_effort'))
    csv_row.append(advertised_course_run.get('max_effort'))
    csv_row.append(advertised_course_run.get('weeks_to_complete'))  # Length

    csv_row.append(strip_tags(hit.get('outcome', '')))  # What You’ll Learn

    csv_row.append(strip_tags(hit.get('prerequisites_raw', '')))  # Pre-requisites

    catalogs = fetch_catalog_types(hit)  # Catalog types
    csv_row.append(', '.join(catalogs))

    return csv_row


def fetch_and_format_registration_date(obj):
    enroll_by_date = obj.get('registration_deadline')
    stripped_enroll_by = enroll_by_date.split("T")[0]
    formatted_enroll_by = None
    try:
        enroll_by_datetime_obj = datetime.datetime.strptime(stripped_enroll_by, '%Y-%m-%d')
        formatted_enroll_by = enroll_by_datetime_obj.strftime('%m-%d-%Y')
    except ValueError as exc:
        logger.info(f"Unable to format registration deadline, failed with error: {exc}")
    return formatted_enroll_by


def exec_ed_course_to_row(hit):
    """
    Helper function to construct a CSV row according to a single executive education course hit.
    """
    csv_row = []
    csv_row.append(hit.get('title'))

    if hit.get('partners'):
        csv_row.append(hit['partners'][0]['name'])
    else:
        csv_row.append(None)
    if hit.get('additional_metadata'):
        start_date = None
        additional_md = hit['additional_metadata']
        if additional_md.get('start_date'):
            start_date = parser.parse(additional_md['start_date']).strftime(DATE_FORMAT)
        csv_row.append(start_date)

        end_date = None
        if additional_md.get('end_date'):
            end_date = parser.parse(additional_md['end_date']).strftime(DATE_FORMAT)
        csv_row.append(end_date)
        formatted_enroll_by = fetch_and_format_registration_date(additional_md)
    else:
        csv_row.append(None)  # no start date
        csv_row.append(None)  # no end date
        formatted_enroll_by = None

    csv_row.append(formatted_enroll_by)

    adv_course_run = hit.get('advertised_course_run', {})
    key = adv_course_run.get('key')

    price = float(hit['entitlements'][0]['price'])
    csv_row.append(math.trunc(price))
    csv_row.append(hit.get('language'))
    csv_row.append(', '.join(hit.get('transcript_languages', [])))
    csv_row.append(hit.get('marketing_url'))
    csv_row.append(strip_tags(hit.get('short_description', '')))

    csv_row.append(', '.join(hit.get('subjects', [])))
    csv_row.append(key)
    csv_row.append(hit.get('aggregation_key'))

    skills = [skill['name'] for skill in hit.get('skills', [])]
    csv_row.append(', '.join(skills))

    csv_row.append(adv_course_run.get('min_effort'))
    csv_row.append(adv_course_run.get('max_effort'))
    csv_row.append(adv_course_run.get('weeks_to_complete'))  # Length

    csv_row.append(strip_tags(hit.get('outcome', '')))  # What You’ll Learn

    csv_row.append(strip_tags(hit.get('full_description', '')))

    return csv_row


def course_hit_runs(hit):
    """
    Helper function to extract the course runs (list) or return empty list
    """
    return hit.get('course_runs', [])


def course_run_to_row(hit, course_run):
    """
    Helper function to construct a CSV row corresponding to a single course_run.
    """
    csv_row = []
    csv_row.append(hit.get('title'))
    csv_row.append(course_run.get('key'))
    csv_row.append(hit.get('aggregation_key'))
    csv_row.append(course_run.get('pacing_type'))
    csv_row.append(course_run.get('availability'))

    start_date = None
    if course_run.get('start'):
        start_date = parser.parse(course_run.get('start')).strftime(DATE_FORMAT)
    csv_row.append(start_date)

    end_date = None
    if course_run.get('end'):
        end_date = parser.parse(course_run.get('end')).strftime(DATE_FORMAT)
    csv_row.append(end_date)

    upgrade_deadline = None
    if course_run.get('upgrade_deadline'):
        raw_deadline = course_run.get('upgrade_deadline')
        upgrade_deadline = datetime.datetime.fromtimestamp(raw_deadline).strftime(DATE_FORMAT)
    csv_row.append(upgrade_deadline)

    # Min Effort
    csv_row.append(course_run.get('min_effort'))

    # Max Effort
    csv_row.append(course_run.get('max_effort'))

    # Length
    csv_row.append(course_run.get('weeks_to_complete'))

    # Program Type
    csv_row.append(', '.join(hit.get('program_titles', [])))

    # Programs
    csv_row.append(', '.join(hit.get('programs', [])))

    # Skills
    skills = [skill['name'] for skill in hit.get('skills', [])]
    csv_row.append(', '.join(skills))

    # Subjects
    csv_row.append(', '.join(hit.get('subjects', [])))

    # Language
    csv_row.append(hit.get('language'))

    # Subtitles
    csv_row.append(', '.join(hit.get('transcript_languages', [])))

    # Course Catalogs
    catalogs = fetch_catalog_types(hit)
    csv_row.append(', '.join(catalogs))

    return csv_row


def hit_to_row(hit):
    """
    Maintain the legacy API for now.
    """
    return course_hit_to_row(hit)


def querydict_to_dict(query_dict):
    """
    Utility function to easily retrieve lists from the params in a QueryDict
    """
    data = {}
    for key in query_dict.keys():
        v = query_dict.getlist(key)
        data[key] = v
    return data


def facets_to_query(facets):
    """
    Helper function to extract the search query out of a given set of facet params.
    """
    if facets.get('query'):
        # comes out as a list, we want the first value string only
        return facets.pop('query')[0]
    elif facets.get('q'):
        # comes out as a list, we want the first value string only
        return facets.pop('q')[0]
    else:
        return ''


def get_valid_facets():
    valid_facets = []
    for facet in ALGOLIA_INDEX_SETTINGS['attributesForFaceting']:
        # Because this is pulled from the settings `attributesForFaceting`, we need to strip potential `searchable()`
        # wrappers
        valid_facets.append(facet.replace('searchable(', '').rstrip(')'))
    return valid_facets


def validate_query_facets(facets):
    """
    Verify that provided query facet params are valid Algolia facets.
    """
    invalid_facets = []
    for facet in facets.keys():
        if facet not in get_valid_facets():
            invalid_facets.append(facet)
    return invalid_facets
