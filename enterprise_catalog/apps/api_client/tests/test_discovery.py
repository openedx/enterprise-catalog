""" Tests for discovery api client. """

import mock
from django.test import TestCase

from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.tests.factories import CatalogQueryFactory


class TestDiscoveryApiClient(TestCase):
    """ DiscoveryApiClient tests. """

    @mock.patch('enterprise_catalog.apps.api_client.discovery.OAuthAPIClient')
    def test_get_metadata_by_query(self, mock_oauth_client):
        """
        get_metadata_by_query should call discovery endpoint, but not call
        traverse_pagination if traverse_pagination is false.
        """
        mock_oauth_client.return_value.post.return_value.json.return_value = {
            'results': [{'key': 'fakeX'}],
        }

        catalog_query = CatalogQueryFactory()
        query_params = {'exclude_expired_course_run': True}
        client = DiscoveryApiClient()
        actual_response = client.get_metadata_by_query(catalog_query, query_params)

        mock_oauth_client.return_value.post.assert_called_once()

        expected_response = [{'key': 'fakeX'}]
        self.assertEqual(actual_response, expected_response)
