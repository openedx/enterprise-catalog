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
    'Enroll-by Date',
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
    'Enroll-by Date',
    'Price',
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


def _base_csv_row_data(hit):
    """ Returns the formatted, shared attributes common across all course types. """
    title = hit.get('title')
    aggregation_key = hit.get('aggregation_key')
    language = hit.get('language')
    transcript_languages = ', '.join(hit.get('transcript_languages', []))
    marketing_url = hit.get('marketing_url')
    short_description = strip_tags(hit.get('short_description', ''))
    subjects = ', '.join(hit.get('subjects', []))
    skills = ', '.join([skill['name'] for skill in hit.get('skills', [])])
    outcome = strip_tags(hit.get('outcome', ''))  # What You’ll Learn

    # FIXME: currently ignores partner names when a course has multiple partners
    partner_name = hit['partners'][0]['name'] if hit.get('partners') else None

    empty_advertised_course_run = {}
    advertised_course_run = hit.get('advertised_course_run', empty_advertised_course_run)
    advertised_course_run_key = advertised_course_run.get('key')
    min_effort = advertised_course_run.get('min_effort')
    max_effort = advertised_course_run.get('max_effort')
    weeks_to_complete = advertised_course_run.get('weeks_to_complete')  # Length

    if start_date := advertised_course_run.get('start'):
        start_date = parser.parse(start_date).strftime(DATE_FORMAT)

    if end_date := advertised_course_run.get('end'):
        end_date = parser.parse(end_date).strftime(DATE_FORMAT)

    if enroll_by := advertised_course_run.get('enroll_by'):
        enroll_by = datetime.datetime.fromtimestamp(enroll_by).strftime(DATE_FORMAT)

    content_price = None
    if content_price := advertised_course_run.get('content_price'):
        content_price = math.trunc(float(content_price))
    return {
        'title': title,
        'partner_name': partner_name,
        'start_date': start_date,
        'end_date': end_date,
        'enroll_by': enroll_by,
        'aggregation_key': aggregation_key,
        'advertised_course_run_key': advertised_course_run_key,
        'language': language,
        'transcript_languages': transcript_languages,
        'marketing_url': marketing_url,
        'short_description': short_description,
        'subjects': subjects,
        'skills': skills,
        'min_effort': min_effort,
        'max_effort': max_effort,
        'weeks_to_complete': weeks_to_complete,
        'outcome': outcome,
        'advertised_course_run': advertised_course_run,
        'content_price': content_price
    }


def course_hit_to_row(hit):
    """
    Helper function to construct a CSV row according to a single Algolia result course hit.
    """
    row_data = _base_csv_row_data(hit)
    csv_row = []
    csv_row.append(row_data.get('title'))
    csv_row.append(row_data.get('partner_name'))

    advertised_course_run = row_data.get('advertised_course_run')

    csv_row.append(row_data.get('start_date'))
    csv_row.append(row_data.get('end_date'))

    # upgrade_deadline deprecated in favor of enroll_by
    if upgrade_deadline := advertised_course_run.get('upgrade_deadline'):
        upgrade_deadline = datetime.datetime.fromtimestamp(upgrade_deadline).strftime(DATE_FORMAT)
    csv_row.append(upgrade_deadline)
    csv_row.append(row_data.get('enroll_by'))
    csv_row.append(', '.join(hit.get('programs', [])))
    csv_row.append(', '.join(hit.get('program_titles', [])))

    pacing_type = advertised_course_run.get('pacing_type')
    csv_row.append(pacing_type)

    csv_row.append(hit.get('level_type'))
    csv_row.append(row_data.get('content_price'))
    csv_row.append(row_data.get('language'))
    csv_row.append(row_data.get('transcript_languages'))
    csv_row.append(row_data.get('marketing_url'))
    csv_row.append(row_data.get('short_description'))
    csv_row.append(row_data.get('subjects'))
    csv_row.append(row_data.get('advertised_course_run_key'))
    csv_row.append(row_data.get('aggregation_key'))
    csv_row.append(row_data.get('skills'))
    csv_row.append(row_data.get('min_effort'))
    csv_row.append(row_data.get('max_effort'))
    csv_row.append(row_data.get('weeks_to_complete'))
    csv_row.append(row_data.get('outcome'))

    csv_row.append(strip_tags(hit.get('prerequisites_raw', '')))  # Pre-requisites

    catalogs = fetch_catalog_types(hit)  # Catalog types
    csv_row.append(', '.join(catalogs))

    return csv_row


def exec_ed_course_to_row(hit):
    """
    Helper function to construct a CSV row according to a single executive education course hit.
    """
    row_data = _base_csv_row_data(hit)
    csv_row = []
    csv_row.append(row_data.get('title'))
    csv_row.append(row_data.get('partners'))

    csv_row.append(row_data.get('start_date'))
    csv_row.append(row_data.get('end_date'))
    csv_row.append(row_data.get('enroll_by'))

    csv_row.append(row_data.get('content_price'))
    csv_row.append(row_data.get('language'))
    csv_row.append(row_data.get('transcript_languages'))
    csv_row.append(row_data.get('marketing_url'))
    csv_row.append(row_data.get('short_description'))
    csv_row.append(row_data.get('subjects'))
    csv_row.append(row_data.get('advertised_course_run_key'))
    csv_row.append(row_data.get('aggregation_key'))
    csv_row.append(row_data.get('skills'))
    csv_row.append(row_data.get('min_effort'))
    csv_row.append(row_data.get('max_effort'))
    csv_row.append(row_data.get('weeks_to_complete'))
    csv_row.append(row_data.get('outcome'))
    csv_row.append(strip_tags(hit.get('full_description', '')))

    return csv_row


def course_hit_runs(hit):
    """
    Helper function to extract the course runs (list) or return empty list
    """
    course_runs = [
        course_run
        for course_run in hit.get('course_runs', [])
        if course_run.get('is_active') is True
    ]
    return course_runs


def course_run_to_row(hit, course_run):
    """
    Helper function to construct a CSV row corresponding to a single course_run.

    The order in which you append rows is dependent on the order of CSV_COURSE_RUN_HEADER
    and must be appended in that order
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

    # upgrade_deadline deprecated in favor of enroll_by
    upgrade_deadline = None
    if course_run.get('upgrade_deadline'):
        raw_deadline = course_run.get('upgrade_deadline')
        upgrade_deadline = datetime.datetime.fromtimestamp(raw_deadline).strftime(DATE_FORMAT)
    csv_row.append(upgrade_deadline)

    if enroll_by := course_run.get('enroll_by', None):
        enroll_by = datetime.datetime.fromtimestamp(enroll_by).strftime(DATE_FORMAT)
    csv_row.append(enroll_by)

    if content_price := course_run.get('content_price'):
        content_price = math.trunc(float(content_price))
    csv_row.append(content_price)

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
