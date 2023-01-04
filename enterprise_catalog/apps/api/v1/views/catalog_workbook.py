import io
import logging
import time

import xlsxwriter
from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST

from enterprise_catalog.apps.api.v1 import export_utils
from enterprise_catalog.apps.catalog.algolia_utils import (
    get_initialized_algolia_client,
)


logger = logging.getLogger(__name__)


def write_row_data(row, worksheet, row_num):
    for col_num, cell_data in enumerate(row):
        worksheet.write(row_num, col_num, cell_data)
    return row_num + 1


class CatalogWorkbookView(GenericAPIView):
    """
    Catalog Workbook data generation view. All query params are assumed to be facet filters used to filter indexed data
    whenv searching. All distinct facets provided are interpreted as a conjunction (AND), however multiple identical
    facets query params use a disjunction (OR).

    Returns:
        A Workbook file correlating to filtered Algolia catalog metadata.
    """
    permission_classes = []

    # pylint: disable=too-many-statements
    @action(detail=True)
    def get(self, request, **kwargs):
        """
        GET entry point for the `CatalogWorkbookView`
        """
        facets = export_utils.querydict_to_dict(request.query_params)
        algoliaQuery = export_utils.facets_to_query(facets)

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
        header_format = workbook.add_format({'bold': True})

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

        if len(page['hits']) == 0:
            return Response(f'Error: invalid query: {algoliaQuery} provided.', status=HTTP_400_BAD_REQUEST)

        # content row index, starting at 1 which is after header row
        course_row_num = 1
        program_row_num = 1
        course_run_row_num = 1
        exec_ed_row_num = 1
        exec_ed_results_found = False
        edx_course_results_found = False
        edx_program_results_found = False
        course_run_results_found = False
        while len(page['hits']) > 0:
            for hit in page.get('hits', []):
                if hit.get('content_type') == 'course':
                    is_exec_ed = hit.get('course_type') == 'executive-education-2u'
                    if is_exec_ed:
                        if not exec_ed_results_found:
                            exec_ed_results_found = True
                            exec_ed_worksheet = workbook.add_worksheet('Executive Education')
                            export_utils.write_headers_to_sheet(
                                exec_ed_worksheet, export_utils.CSV_EXEC_ED_COURSE_HEADERS, header_format
                            )
                        course_row = export_utils.exec_ed_course_to_row(hit)
                        exec_ed_row_num = write_row_data(course_row, exec_ed_worksheet, exec_ed_row_num)
                    else:
                        if not edx_course_results_found:
                            edx_course_results_found = True
                            course_worksheet = workbook.add_worksheet('Courses')
                            export_utils.write_headers_to_sheet(
                                course_worksheet, export_utils.CSV_COURSE_HEADERS, header_format
                            )
                        course_row = export_utils.course_hit_to_row(hit)
                        course_row_num = write_row_data(course_row, course_worksheet, course_row_num)
                    for course_run in export_utils.course_hit_runs(hit):
                        if not course_run_results_found:
                            course_run_results_found = True
                            course_run_worksheet = workbook.add_worksheet('Course Runs')
                            export_utils.write_headers_to_sheet(
                                course_run_worksheet, export_utils.CSV_COURSE_RUN_HEADERS, header_format
                            )
                        course_run_row = export_utils.course_run_to_row(hit, course_run)
                        course_run_row_num = write_row_data(course_run_row, course_run_worksheet, course_run_row_num)
                if hit.get('content_type') == 'program':
                    if not edx_program_results_found:
                        edx_program_results_found = True
                        program_worksheet = workbook.add_worksheet('Programs')
                        export_utils.write_headers_to_sheet(
                            program_worksheet, export_utils.CSV_PROGRAM_HEADERS, header_format
                        )
                    program_row = export_utils.program_hit_to_row(hit)
                    program_row_num = write_row_data(program_row, program_worksheet, program_row_num)
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
        filename = f'Enterprise-Catalog-Export-{time.strftime("%Y%m%d%H%M%S")}.xlsx'
        response['Content-Disposition'] = f'attachment; filename={filename}'

        return response
