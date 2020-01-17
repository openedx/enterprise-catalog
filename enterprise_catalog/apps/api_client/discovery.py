# -*- coding: utf-8 -*-
"""
Discovery service api client code.
"""

from django.conf import settings

from urllib.parse import urljoin

from edx_rest_api_client.client import OAuthAPIClient


class DiscoveryApiClient(object):
    """
    Object builds an API client to make calls to the the Discovery Service.
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

    def traverse_pagination(self, response, content_filter_query, query_params):
        """
        Traverse a paginated API response and extracts and concatenates "results"
        returned by API.

        response (dict): API response object.
        content_filter_query (dict): query parameters used to filter catalog results.
        query_params (dict): query parameters used to paginate results.

        Return a list (all the results returned by the API).
        """
        results = response.get('results', [])

        page = 1
        while response.get('next'):
            page += 1
            query_params.update({'page': page})
            response = self.client.post(
                self.SEARCH_ALL_ENDPOINT,
                data=content_filter_query,
                **query_params
            ).json()
            results += response.get('results', [])

        return results

    def get_metadata_by_query(self, content_filter_query, query_params=None, traverse_pagination=False):
        """
        Return results from the discovery service's search/all endpoint.

        content_filter_query (dict): some elasticsearch filter
            e.g. - {'aggregation_key': 'course-v1:some+key+here'}
        query_params (dict): additional query params for the rest api endpoint
             we're hitting. e.g. - {'page': 3}
        traverse_pagination (bool): determine if we should iterate over all
            pages of results for given query

        Returns a dictionary.
        """
        if query_params is None:
            query_params = {}

        response = self.client.post(
            self.SEARCH_ALL_ENDPOINT,
            data=content_filter_query,
            **query_params
        ).json()

        if traverse_pagination:
            response['results'] = self.traverse_pagination(
                self.SEARCH_ALL_ENDPOINT,
                response,
                content_filter_query,
                query_params
            )

            response['next'] = response['previous'] = None

        return response
