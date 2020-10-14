"""
Discovery service api client code.
"""
import logging

from celery.exceptions import SoftTimeLimitExceeded

from .base_oauth import BaseOAuthClient
from .constants import (
    DISCOVERY_COURSES_ENDPOINT,
    DISCOVERY_OFFSET_SIZE,
    DISCOVERY_SEARCH_ALL_ENDPOINT,
)


LOGGER = logging.getLogger(__name__)


class DiscoveryApiClient(BaseOAuthClient):
    """
    Object builds an API client to make calls to the Discovery Service.
    """

    def _retrieve_metadata_for_content_filter(self, content_filter, page, request_params):
        """
        Makes a request to discovery's /search/all/ endpoint with the specified
        content_filter, page, and request_params
        """
        LOGGER.info(f'Retrieving results from course-discovery for page {page}...')
        response = self.client.post(
            DISCOVERY_SEARCH_ALL_ENDPOINT,
            json=content_filter,
            params=request_params,
        ).json()
        return response

    def get_metadata_by_query(self, catalog_query, query_params=None):
        """
        Return results from the discovery service's search/all endpoint.

        Arguments:
            content_filter_query (dict): some elasticsearch filter
                e.g. - {'aggregation_key': 'course-v1:some+key+here'}
            query_params (dict): additional query params for the rest api endpoint
                we're hitting. e.g. - {'page': 3}

        Returns:
            list: a list of the results, or None if there was an error calling the discovery service.
        """
        request_params = {}
        request_params.update(query_params or {})

        page = 1
        results = []
        try:
            content_filter = catalog_query.content_filter
            response = self._retrieve_metadata_for_content_filter(content_filter, page, request_params)
            results += response.get('results', [])
            # Traverse all pages and concatenate results
            while response.get('next'):
                page += 1
                request_params.update({'page': page})
                response = self._retrieve_metadata_for_content_filter(content_filter, page, request_params)
                results += response.get('results', [])
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.error(
                'Could not retrieve content items from course-discovery (page %s) for catalog query %s: %s',
                page,
                catalog_query,
                exc,
            )
            # if a request to discovery fails, return `None` so that callers of this
            # method are aware we weren't able to get all metadata for the given query
            return None

        return results

    def _retrieve_courses(self, offset, request_params):
        """
        Makes a request to discovery's /api/v1/courses/ endpoint with the specified offset and request_params
        """
        LOGGER.info(f'Retrieving courses from course-discovery for offset {offset}...')
        response = self.client.get(
            DISCOVERY_COURSES_ENDPOINT,
            params=request_params,
        ).json()
        return response

    def get_courses(self, query_params=None):
        """
        Return results from the discovery service's /courses endpoint.

        Arguments:
            query_params (dict): additional query params for the rest api endpoint
                we're hitting. e.g. - {'limit': 100}

        Returns:
            list: a list of the results, or None if there was an error calling the discovery service.
        """
        request_params = {'limit': DISCOVERY_OFFSET_SIZE}
        request_params.update(query_params or {})

        courses = []
        offset = 0
        try:
            response = self._retrieve_courses(offset, request_params)
            courses += response.get('results')
            # Traverse all pages and concatenate results
            while response.get('next'):
                offset += DISCOVERY_OFFSET_SIZE
                request_params.update({'offset': offset})
                response = self._retrieve_courses(offset, request_params)
                courses += response.get('results', [])
        except SoftTimeLimitExceeded as exc:
            LOGGER.warning(
                'A task reached the soft time limit while traversing courses. %d courses already retrieved'
                ' from course-discovery will continue to be processed: %s',
                len(courses),
                exc,
            )
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.error(
                'Could not get courses from course-discovery (offset %d) with query params %s: %s',
                offset,
                request_params,
                exc,
            )

        return courses
