#!/usr/bin/python
"""
Script to make manual requests against the Discovery Service (in some environment).

You can set up secrets and target hosts using environment variables.  A minimal useful set is:

export OAUTH_BASE_URL=https://courses.stage.edx.org/
export OAUTH_CLIENT_ID={your oauth2 application ID}
export OAUTH_CLIENT_SECRET={your oauth2 application secret}
export DISCOVERY_SERVICE_API_URL=https://discovery.stage.edx.org/api/v1/

It might be useful to save these in a file that you can easily copy/paste into your app container shell.

Can execute as `python -m scripts.discovery_query` straight from the command line.

Or, enter a python shell and import it:

from scripts.discovery_query import *
results = get_metadata_from_content_filter()
pprint(results[0])

"""
import os
from pprint import pprint

from enterprise_catalog.apps.api_client.discovery import *


class ScriptingDiscoveryClient(DiscoveryApiClient):
    """
    Object builds an API client to make calls to the Discovery Service.
    """
    def __init__(
        self, oauth_base_url=None, oauth_client_id=None,
        oauth_client_secret=None, discovery_service_api_url=None
    ):
        self._oauth_base_url = oauth_base_url
        self._oauth_client_id = oauth_client_id
        self._oauth_client_secret = oauth_client_secret
        self._discovery_service_api_url = discovery_service_api_url

        self.client = OAuthAPIClient(
            self.oauth_base_url,
            self.oauth_client_id,
            self.oauth_client_secret,
        )

    @property
    def oauth_base_url(self):
        # For example: https://courses.edx.org/
        from_env = os.environ.get('OAUTH_BASE_URL')
        result = self._oauth_base_url or from_env
        assert result, 'OAUTH_BASE_URL must be set in env or provided to client on init!'
        return result

    @property
    def oauth_client_id(self):
        from_env = os.environ.get('OAUTH_CLIENT_ID')
        result = self._oauth_client_id or from_env
        assert result, 'OAUTH_CLIENT_ID must be set in env or provided to client on init!'
        return result

    @property
    def oauth_client_secret(self):
        from_env = os.environ.get('OAUTH_CLIENT_SECRET')
        result = self._oauth_client_secret or from_env
        assert result, 'OAUTH_CLIENT_SECRET must be set in env or provided to client on init!'
        return result

    @property
    def SEARCH_ALL_ENDPOINT(self):
        """
        Yes, this is, indeed, unconventional.
        For example: https://discovery.edx.org/api/v1 
        """
        from_env = os.environ.get('DISCOVERY_SERVICE_API_URL')
        result = self._discovery_service_api_url or from_env
        assert result, 'DISCOVERY_SERVICE_API_URL must be set in env or provided to client on init!'
        return urljoin(result, self.SEARCH_ALL_EXTENSION)

    def get_metadata_by_query(self, content_filter_query, query_params=None, traverse_pagination=False):
        """
        Return results from the discovery service's search/all endpoint.

        content_filter_query (dict): some elasticsearch filter
            e.g. - {'aggregation_key': 'course-v1:some+key+here'}
        query_params (dict): additional query params for the rest api endpoint
            we're hitting. e.g. - {'page': 3}
        traverse_pagination (boolean): If true, will traverse the paginated responses from the endpoint.
            Defaults to False.

        Returns a list of the results.
        """
        if query_params is None:
            query_params = {}

        response = self.client.post(
            self.SEARCH_ALL_ENDPOINT,
            json=content_filter_query,
            params=query_params
        ).json()

        results = response.get('results', [])
        if not traverse_pagination:
            return results

        page = 1
        while response.get('next'):
            page += 1
            query_params.update({'page': page})
            response = self.client.post(
                self.SEARCH_ALL_ENDPOINT,
                json=content_filter_query,
                params=query_params
            ).json()
            results += response.get('results', [])

        return results


def get_metadata_from_content_filter(**client_kwargs):
    """
    An example function to make a request against the discovery service's `search/all` endpoint.
    """
    disco_client = ScriptingDiscoveryClient(**client_kwargs)
    content_filter = {
        'availability': ['Current', 'Starting Soon', 'Upcoming'],
        'content_type': 'course',
        'partner': 'edx',
        'level_type': ['Introductory', 'Intermediate', 'Advanced']
    }
    results = disco_client.get_metadata_by_query(content_filter)
    return results


if __name__ == '__main__':
    get_metadata_from_content_filter()
