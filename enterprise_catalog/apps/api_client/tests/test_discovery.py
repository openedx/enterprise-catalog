""" Tests for discovery api client. """

import mock
from django.test import TestCase

from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient


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

        content_filter = {'*': '*'}
        client = DiscoveryApiClient()
        actual_response = client.get_metadata_by_query(content_filter)

        mock_oauth_client.return_value.get.assert_called_once()

        expected_response = [{'key': 'fakeX'}]
        self.assertEqual(actual_response, expected_response)
