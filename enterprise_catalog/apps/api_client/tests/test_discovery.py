""" Tests for discovery api client. """

import mock
from django.test import TestCase
from simplejson import JSONDecodeError

from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.tests.factories import CatalogQueryFactory


class TestDiscoveryApiClient(TestCase):
    """ DiscoveryApiClient tests. """

    @mock.patch('enterprise_catalog.apps.api_client.base_oauth.OAuthAPIClient')
    def test_get_metadata_by_query_with_results(self, mock_oauth_client):
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

    @mock.patch('enterprise_catalog.apps.api_client.base_oauth.OAuthAPIClient')
    def test_get_metadata_by_query_with_error(self, mock_oauth_client):
        """
        get_metadata_by_query should return None when a call to discovery endpoint fails.
        """
        mock_oauth_client.return_value.post.side_effect = JSONDecodeError('error', '{}', 0)

        catalog_query = CatalogQueryFactory()
        query_params = {'exclude_expired_course_run': True}
        client = DiscoveryApiClient()
        actual_response = client.get_metadata_by_query(catalog_query, query_params)

        mock_oauth_client.return_value.post.assert_called_once()

        expected_response = None
        self.assertEqual(actual_response, expected_response)

    @mock.patch('enterprise_catalog.apps.api_client.base_oauth.OAuthAPIClient')
    def test_get_courses_with_results(self, mock_oauth_client):
        """
        get_courses should call discovery endpoint to fetch all courses
        """
        mock_oauth_client.return_value.get.return_value.json.return_value = {
            'results': [{'key': 'fakeX'}],
        }

        query_params = {'ordering': 'key'}
        client = DiscoveryApiClient()
        actual_response = client.get_courses(query_params)

        mock_oauth_client.return_value.get.assert_called_once()

        expected_response = [{'key': 'fakeX'}]
        self.assertEqual(actual_response, expected_response)

    @mock.patch('enterprise_catalog.apps.api_client.base_oauth.OAuthAPIClient')
    def test_get_courses_with_error(self, mock_oauth_client):
        """
        get_courses should return empty list when a call to discovery endpoint fails.
        """
        mock_oauth_client.return_value.get.side_effect = JSONDecodeError('error', '{}', 0)

        query_params = {'ordering': 'key'}
        client = DiscoveryApiClient()
        actual_response = client.get_courses(query_params)

        mock_oauth_client.return_value.get.assert_called_once()

        expected_response = []
        self.assertEqual(actual_response, expected_response)
