import codecs
import csv
import time

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
from enterprise_catalog.apps.catalog.constants import TIMESTAMP_FORMAT


# CatalogCsvView's StreamingHttpResponse requires a File-like class that has a 'write' method
class Echo:
    """An object that implements just the write method of the file-like
    interface.
    """
    def write(self, value):
        """Write the value by returning it, instead of storing in a buffer."""
        return value


class CatalogCsvView(GenericAPIView):
    """
    Catalog CSV data generation view. All query params are assumed to be facet filters used to filter indexed data when
    searching. All distinct facets provided are interpreted as a conjunction (AND), however multiple identical facets
    query params use a disjunction (OR).

    Returns:
        Streams a CSV file correlating to filtered Algolia catalog metadata.
    """
    permission_classes = []

    def iter_items(self, facets, algoliaQuery):
        pseudo_buffer = Echo()
        writer = csv.writer(pseudo_buffer)

        # need a leading BOM for excel-compatible files with UTF-8 content
        yield codecs.BOM_UTF8
        yield writer.writerow(export_utils.CSV_COURSE_HEADERS)

        algolia_client = get_initialized_algolia_client()
        # discovery to gather extra, non-indexed fields
        discovery_client = DiscoveryApiClient()

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
        while len(page['hits']) > 0:
            course_keys_chunk = []
            for hit in page.get('hits', []):
                # ignore program data (for now)
                if hit.get('content_type') != 'course':
                    continue
                if hit.get('key'):
                    course_keys_chunk.append(hit.get('key'))

            # build a lookup dictionary for efficient lookup when combining
            course_by_key = {}
            if len(course_keys_chunk) > 0:
                query_params = {'keys': ','.join(course_keys_chunk)}
                courses = discovery_client.get_courses(query_params=query_params)
                for course in courses:
                    course_by_key[course.get('key')] = course

            # combine discovery metadata with the algolia results
            # append the hit to the results
            for hit in page.get('hits', []):
                # ignore program data (for now)
                if hit.get('content_type') != 'course':
                    continue
                if course_by_key.get(hit.get('key')):
                    hit['discovery_course'] = course_by_key.get(hit.get('key'))
                row = export_utils.hit_to_row(hit)
                yield writer.writerow(row)

            search_options['page'] = search_options['page'] + 1
            page = algolia_client.algolia_index.search(algoliaQuery, search_options)

    @action(detail=True)
    def get(self, request, **kwargs):
        """
        GET entry point for the `CatalogCsvView`
        """
        facets = export_utils.querydict_to_dict(request.query_params)
        if facets.get('query'):
            algoliaQuery = facets.pop('query')
        else:
            algoliaQuery = ''

        invalid_facets = export_utils.validate_query_facets(facets)
        if invalid_facets:
            return Response(f'Error: invalid facet(s): {invalid_facets} provided.', status=HTTP_400_BAD_REQUEST)

        filename = f'Enterprise-Catalog-Export-{time.strftime(TIMESTAMP_FORMAT)}.csv'

        response = StreamingHttpResponse(
            streaming_content=(self.iter_items(facets, algoliaQuery)),
            content_type='text/csv;charset=utf-8',
        )
        response['Content-Disposition'] = f'attachment; filename={filename}'
        return response
