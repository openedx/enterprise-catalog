import codecs
import csv
import time
import xlsxwriter

from django.http import StreamingHttpResponse
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST

from enterprise_catalog.apps.api.v1 import export_utils
from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.algolia_utils import (
    get_initialized_algolia_client,
)


class CatalogWorkbookView(GenericAPIView):
    """
    Catalog Workbook data generation view. All query params are assumed to be facet filters used to filter indexed data when
    searching. All distinct facets provided are interpreted as a conjunction (AND), however multiple identical facets
    query params use a disjunction (OR).

    Returns:
        A Workbook file correlating to filtered Algolia catalog metadata.
    """
    permission_classes = []

    facets = export_utils.querydict_to_dict(request.query_params)
    if facets.get('query'):
        algoliaQuery = facets.pop('query')
    else:
        algoliaQuery = ''

    invalid_facets = export_utils.validate_query_facets(facets)
    if invalid_facets:
        return Response(f'Error: invalid facet(s): {invalid_facets} provided.', status=HTTP_400_BAD_REQUEST)

    # Create an in-memory output file for the new workbook.
    output = io.BytesIO()

    # Even though the final file will be in memory the module uses temp
    # files during assembly for efficiency. To avoid this on servers that
    # don't allow temp files, for example the Google APP Engine, set the
    # 'in_memory' Workbook() constructor option as shown in the docs.
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()

    # write headers
    for col_num, cell_data in enumerate(export_utils.CSV_HEADERS):
        worksheet.write(0, col_num, cell_data)

    algolia_client = get_initialized_algolia_client()

    facet_filters = []
    for facet_name, facet_values in facets.items():
        combined_facets = []
        for facet_value in facet_values:
            combined_facets.append(f'{facet_name}:{facet_value}')
        facet_filters.append(combined_facets)

    search_options = {
        'facetFilters': facet_filters,
        'attributesToRetrieve': export_utils.ALGOLIA_ATTRIBUTES_TO_RETRIEVE,
        'hitsPerPage': 100,
        'page': 0,
        }

    # Algolia search will only retrieve all results if you query by empty string.
    page = algolia_client.algolia_index.search(algoliaQuery, search_options)
    row_num = 1 # start after header row
    while len(page['hits']) > 0:
        for hit in page.get('hits', []):
            # ignore program data (for now)
            if hit.get('content_type') != 'course':
                continue
            row = export_utils.hit_to_row(hit)
            # Write some test data.
            for row_num, columns in enumerate(row):
                for col_num, cell_data in enumerate(columns):
                    worksheet.write(row_num, col_num, cell_data)            
            row_num = row_num + 1
        search_options['page'] = search_options['page'] + 1
        page = algolia_client.algolia_index.search(algoliaQuery, search_options)

    # Close the workbook before sending the data.
    workbook.close()

    # Rewind the buffer.
    output.seek(0)

    # Set up the Http response.
    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f'Enterprise-Catalog-Export-{time.strftime("%Y%m%d%H%M%S")}.xls'
    response['Content-Disposition'] = f'attachment; filename={filename}'

    return response
