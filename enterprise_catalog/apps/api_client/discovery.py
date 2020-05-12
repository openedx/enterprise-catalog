# -*- coding: utf-8 -*-
"""
Discovery service api client code.
"""

from urllib.parse import urljoin

from django.conf import settings
from edx_rest_api_client.client import OAuthAPIClient


class DiscoveryApiClient:
    """
    Object builds an API client to make calls to the Discovery Service.
    """
    SEARCH_ALL_EXTENSION = 'search/all/'
    SEARCH_ALL_ENDPOINT = urljoin(settings.DISCOVERY_SERVICE_API_URL, SEARCH_ALL_EXTENSION)

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

    def get_metadata_by_query(self, content_filter_query):
        """
        Return results from the discovery service's search/all endpoint.

        content_filter_query (dict): some elasticsearch filter
            e.g. - {'aggregation_key': 'course-v1:some+key+here'}
        query_params (dict): additional query params for the rest api endpoint
             we're hitting. e.g. - {'page': 3}
        traverse_pagination (bool): determine if we should iterate over all
            pages of results for given query

        Returns a list of the results.
        """
        query_params = {}
        query_params.update(**content_filter_query)
        # Omit non-active course runs from the course-discovery results
        query_params['exclude_expired_course_run'] = True

        response = self.client.get(
            self.SEARCH_ALL_ENDPOINT,
            params=query_params
        ).json()

        results = response.get('results', [])
        page = 1
        while response.get('next'):
            page += 1
            query_params['page'] = page
            response = self.client.get(
                self.SEARCH_ALL_ENDPOINT,
                params=query_params
            ).json()
            results += response.get('results', [])

        return results
