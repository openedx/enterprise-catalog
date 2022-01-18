import datetime
import logging

from dateutil import parser
from django.utils.html import strip_tags

from enterprise_catalog.apps.catalog.algolia_utils import ALGOLIA_INDEX_SETTINGS


logger = logging.getLogger(__name__)

CSV_HEADERS = [
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
]

ALGOLIA_ATTRIBUTES_TO_RETRIEVE = [
    'title',
    'key',
    'content_type',
    'partners',
    'advertised_course_run',
    'programs',
    'program_titles',
    'level_type',
    'language',
    'short_description',
    'subjects',
    'aggregation_key',
    'skills',
    'first_enrollable_paid_seat_price',
    'marketing_url',
]


def hit_to_row(hit):
    # pylint: disable=too-many-statements
    """
    Helper function to construct a CSV row according to a single Algolia result hit.
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
            start_date = parser.parse(hit['advertised_course_run']['start']).strftime("%Y-%m-%d")
        csv_row.append(start_date)

        end_date = None
        if hit['advertised_course_run'].get('end'):
            end_date = parser.parse(hit['advertised_course_run']['end']).strftime("%Y-%m-%d")
        csv_row.append(end_date)

        upgrade_deadline = None
        if hit['advertised_course_run'].get('upgrade_deadline'):
            raw_deadline = hit['advertised_course_run']['upgrade_deadline']
            upgrade_deadline = datetime.datetime.fromtimestamp(raw_deadline).strftime("%Y-%m-%d")
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
    csv_row.append(hit.get('marketing_url'))
    csv_row.append(strip_tags(hit.get('short_description', '')))

    csv_row.append(', '.join(hit.get('subjects', [])))
    csv_row.append(key)
    csv_row.append(hit.get('aggregation_key'))

    skills = [skill['name'] for skill in hit.get('skills', [])]
    csv_row.append(', '.join(skills))

    discovery_course = hit.get('discovery_course', {})
    discovery_course_runs = discovery_course.get('course_runs', [])

    try:
        discovery_first_course_run = discovery_course_runs[0]
    except IndexError:
        discovery_first_course_run = {}

    # Min Effort
    csv_row.append(discovery_first_course_run.get('min_effort'))

    # Max Effort
    csv_row.append(discovery_first_course_run.get('max_effort'))

    # Length
    csv_row.append(discovery_first_course_run.get('weeks_to_complete'))

    # What You’ll Learn -> outcome
    csv_row.append(strip_tags(discovery_course.get('outcome', '')))

    # Pre-requisites -> prerequisites_raw
    csv_row.append(strip_tags(discovery_course.get('prerequisites_raw', '')))

    return csv_row


def querydict_to_dict(query_dict):
    """
    Utility function to easily retrieve lists from the params in a QueryDict
    """
    data = {}
    for key in query_dict.keys():
        v = query_dict.getlist(key)
        data[key] = v
    return data


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
