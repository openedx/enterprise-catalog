# -*- coding: utf-8 -*-
"""
Discovery service api client code.
"""
import logging
from urllib.parse import urljoin

from django.conf import settings
from edx_rest_api_client.client import OAuthAPIClient


LOGGER = logging.getLogger(__name__)

OFFSET_SIZE = 100


class DiscoveryApiClient:
    """
    Object builds an API client to make calls to the Discovery Service.
    """
    SEARCH_ALL_ENDPOINT = urljoin(settings.DISCOVERY_SERVICE_API_URL, 'search/all/')
    COURSES_ENDPOINT = urljoin(settings.DISCOVERY_SERVICE_API_URL, 'courses/')

    def __init__(self):
        self.client = OAuthAPIClient(
            settings.SOCIAL_AUTH_EDX_OAUTH2_URL_ROOT.strip('/'),
            self.oauth2_client_id,
            self.oauth2_client_secret
        )

    @property
    def oauth2_client_id(self):
        return settings.BACKEND_SERVICE_EDX_OAUTH2_KEY

    @property
    def oauth2_client_secret(self):
        return settings.BACKEND_SERVICE_EDX_OAUTH2_SECRET

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
            LOGGER.info('Retrieving results from course-discovery for page {}...'.format(page))
            response = self.client.post(
                self.SEARCH_ALL_ENDPOINT,
                json=catalog_query.content_filter,
                params=request_params,
            ).json()
            results += response.get('results', [])

            # Traverse all pages and concatenate results
            while response.get('next'):
                page += 1
                request_params.update({'page': page})
                LOGGER.info('Retrieving results from course-discovery for page {}...'.format(page))
                response = self.client.post(
                    self.SEARCH_ALL_ENDPOINT,
                    json=catalog_query.content_filter,
                    params=request_params,
                ).json()
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

    def get_courses(self, query_params=None):
        """
        Return results from the discovery service's /courses endpoint.

        Arguments:
            query_params (dict): additional query params for the rest api endpoint
                we're hitting. e.g. - {'limit': 100}

        Returns:
            list: a list of the results, or None if there was an error calling the discovery service.
        """
        request_params = {'limit': OFFSET_SIZE}
        request_params.update(query_params or {})

        courses = []
        offset = 0
        try:
            LOGGER.info('Retrieving courses from course-discovery for offset {}...'.format(offset))
            response = self.client.get(
                self.COURSES_ENDPOINT,
                params=request_params,
            ).json()
            courses += response.get('results', [])

            # Traverse all pages and concatenate results
            while response.get('next'):
                offset += OFFSET_SIZE
                request_params.update({'offset': offset})
                LOGGER.info('Retrieving courses from course-discovery for offset {}...'.format(offset))
                response = self.client.get(
                    self.COURSES_ENDPOINT,
                    params=request_params,
                ).json()
                courses += response.get('results', [])
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.error(
                'Could not get courses from course-discovery (offset %d) with query params %s: %s',
                offset,
                request_params,
                exc,
            )
            courses = []

        return courses
