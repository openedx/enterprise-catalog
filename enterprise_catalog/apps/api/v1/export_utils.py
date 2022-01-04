import csv
import datetime
import logging
from io import BytesIO, StringIO

import xlsxwriter

from enterprise_catalog.apps.catalog.algolia_utils import (
    ALGOLIA_INDEX_SETTINGS,
    get_initialized_algolia_client,
)


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
]

ALGOLIA_ATTRIBUTES_TO_RETRIEVE = [
    'title',
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

def hit_to_row(hit):
    """
    Helper function to construct a CSV row according to a single Algolia result hit.
    """
    csv_row = []
    csv_row.append(hit.get('title', 'No title'))

    if hit.get('partners'):
        csv_row.append(hit['partners'][0]['name'])
    else:
        csv_row.append('No partners')

    if hit.get('advertised_course_run'):
        csv_row.append(hit['advertised_course_run']['start'])

        end = hit['advertised_course_run'].get('end')
        if not end:
            end = 'No end date'
        csv_row.append(end)

        upgrade_deadline = hit['advertised_course_run'].get('upgrade_deadline')
        if upgrade_deadline:
            upgrade_deadline = datetime.datetime.fromtimestamp(upgrade_deadline)
        else:
            upgrade_deadline = 'No upgrade deadline'
        csv_row.append(upgrade_deadline)

        pacing_type = hit['advertised_course_run']['pacing_type']
        key = hit['advertised_course_run'].get('key', 'No key')
    else:
        csv_row.append('No start date')
        csv_row.append('No end date')
        csv_row.append('No upgrade deadline')
        pacing_type = None
        key = 'No key'

    programs = hit.get('programs')
    if not programs:
        programs = 'No program'
    csv_row.append(programs)

    program_titles = hit.get('program_titles')
    if not program_titles:
        program_titles = 'No program'
    csv_row.append(program_titles)

    if not pacing_type:
        pacing_type = 'No pacing type'
    csv_row.append(pacing_type)

    csv_row.append(hit.get('level_type', 'No level_type'))

    csv_row.append(hit.get('first_enrollable_paid_seat_price', 'No price'))
    csv_row.append(hit.get('language', 'No language'))
    csv_row.append(hit.get('marketing_url', 'No url'))
    csv_row.append(hit.get('short_description', 'No short description'))

    csv_row.append(str(hit.get('subjects', 'No subjects')))
    csv_row.append(key)
    csv_row.append(hit.get('aggregation_key', 'No aggregation key'))

    skills = [skill['name'] for skill in hit.get('skills', [])]
    csv_row.append(str(skills))
    return csv_row

def retrieve_indexed_data(facets, algoliaQuery):
    """
    Helper function to retrieve and format indexed Algolia data into a CSV format.
    """
    algolia_client = get_initialized_algolia_client()

    facet_filters = []
    for facet_name, facet_values in facets.items():
        combined_facets = []
        for facet_value in facet_values:
            combined_facets.append(f'{facet_name}:{facet_value}')
        facet_filters.append(combined_facets)

    # Algolia search will only retrieve all results if you query by empty string.
    algolia_hits = algolia_client.algolia_index.browse_objects({
        'query': algoliaQuery,
        'facetFilters': facet_filters,
        'attributesToRetrieve': ALGOLIA_ATTRIBUTES_TO_RETRIEVE
    })
    return algolia_hits

def query_to_csv(facets, algoliaQuery):
	algolia_hits = retrieve_indexed_data(facets, algoliaQuery)
	with StringIO() as file:
	    writer = csv.writer(file)
	    writer.writerow(CSV_HEADERS)
	    for hit in algolia_hits:
	        row = hit_to_row(hit)
	        writer.writerow(row)
	    return file.getvalue()

def query_to_workbook(facets, algoliaQuery):
	# Create an in-memory output file for the new workbook.
	output = BytesIO()
	workbook = xlsxwriter.Workbook(output)
	worksheet = workbook.add_worksheet()
	algolia_hits = retrieve_indexed_data(facets, algoliaQuery)

	# write headers
	for col_num, cell_data in enumerate(CSV_HEADERS):
		worksheet.write(0, col_num, cell_data)

	# write hit data
	for row_num, columns in enumerate(algolia_hits):
		for col_num, cell_data in enumerate(columns):
			row_num = row_num + 1 # account for header row
			worksheet.write(row_num, col_num, cell_data)

	# Close the workbook before sending the data.
	workbook.close()
	# Rewind the buffer.
	output.seek(0)
	return output
