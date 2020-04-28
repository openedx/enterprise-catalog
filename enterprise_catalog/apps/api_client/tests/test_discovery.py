""" Tests for discovery api client. """

import mock
from django.test import TestCase

from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient


class TestDiscoveryApiClient(TestCase):
    """ DiscoveryApiClient tests. """

    @mock.patch('enterprise_catalog.apps.api_client.discovery.DiscoveryApiClient.traverse_pagination')
    @mock.patch('enterprise_catalog.apps.api_client.discovery.OAuthAPIClient')
    def test_get_metadata_by_query_with_traverse(self, mock_oauth_client, mock_traverse):
        """
        get_metadata_by_query should call discovery endpoint, and then call
        traverse_pagination if traverse_pagination is true.
        """
        mock_oauth_client.return_value.post.return_value.json.return_value = {
            'this is': 'just a test'
        }
        mock_traverse.return_value = [{'Title': 'My Title', 'Etc': 'More stuff'}]

        content_filter = {'*': '*'}
        traverse_pagination = True
        query_params = None

        client = DiscoveryApiClient()
        actual_response = client.get_metadata_by_query(
            content_filter,
            query_params,
            traverse_pagination
        )

        mock_oauth_client.return_value.post.assert_called_once()
        mock_traverse.assert_called_once()

        expected_response = {
            'this is': 'just a test',
            'results': [{'Title': 'My Title', 'Etc': 'More stuff'}],
            'next': None,
            'previous': None,
        }
        self.assertDictEqual(actual_response, expected_response)

    @mock.patch('enterprise_catalog.apps.api_client.discovery.DiscoveryApiClient.traverse_pagination')
    @mock.patch('enterprise_catalog.apps.api_client.discovery.OAuthAPIClient')
    def test_get_metadata_by_query_without_traverse(self, mock_oauth_client, mock_traverse):
        """
        get_metadata_by_query should call discovery endpoint, but not call
        traverse_pagination if traverse_pagination is false.
        """
        mock_oauth_client.return_value.post.return_value.json.return_value = {
            'this is': 'just a test'
        }

        content_filter = {'*': '*'}
        traverse_pagination = False
        query_params = {'exclude_expired_course_run': True}

        client = DiscoveryApiClient()
        actual_response = client.get_metadata_by_query(
            content_filter,
            query_params,
            traverse_pagination
        )

        mock_oauth_client.return_value.post.assert_called_once()
        mock_traverse.assert_not_called()

        expected_response = {
            'this is': 'just a test',
        }
        self.assertDictEqual(actual_response, expected_response)

    @mock.patch('enterprise_catalog.apps.api_client.discovery.OAuthAPIClient')
    def test_traverse_pagination(self, mock_oauth_client):
        """
        traverse_pagination should call discovery service and add its results
        to current response dict.
        """
        mock_oauth_client.return_value.post.return_value.json.return_value = {
            'results': [{'item2': 'is from the second page'}],
        }

        current_response_dict = {
            'page': 1,
            'count': '2',
            'previous': None,
            'next': 'url/to/next/page',
            'results': [{'item1': 'is from the first page'}],
        }
        content_filter = {'*': '*'}
        query_params = {}

        client = DiscoveryApiClient()
        actual_results = client.traverse_pagination(
            current_response_dict,
            content_filter,
            query_params
        )
        expected_results = [
            {'item1': 'is from the first page'},
            {'item2': 'is from the second page'},
        ]

        self.assertEqual(actual_results, expected_results)
