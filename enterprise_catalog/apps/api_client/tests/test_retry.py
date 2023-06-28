""" Tests for EnterpriseRery and BaseOAuthClientWithRetry """
from unittest import mock

import requests
import responses
from django.test import TestCase, override_settings
from requests.adapters import Retry
from requests.exceptions import ChunkedEncodingError
from urllib3.exceptions import ConnectTimeoutError

from ..base_oauth_with_retry import BaseOAuthClientWithRetry, EnterpriseRetry
from ..discovery import DiscoveryApiClient


class TestEnterpriseRetry(TestCase):
    """ EnterpriseRetry tests. """

    def test_existing_protocol_error_handling(self):
        """
        Ensure the parent class logic still works
        """
        # pylint: disable=protected-access
        assert EnterpriseRetry()._is_connection_error(ConnectTimeoutError())

    def test_existing_negative_case(self):
        """
        Ensure the parent class logic still works
        """
        # pylint: disable=protected-access
        assert EnterpriseRetry()._is_connection_error(Exception()) is False

    def test_requests_chuncked_error(self):
        """
        Ensure the added Exception(s) are working
        """
        # pylint: disable=protected-access
        assert EnterpriseRetry()._is_connection_error(ChunkedEncodingError())


class TestBaseOAuthClientWithRetry(TestCase):
    """BaseOAuthClientWithRetry tests. """

    # pylint: disable=unexpected-keyword-arg,no-value-for-parameter
    @responses.activate(registry=responses.registries.OrderedRegistry)
    def test_plain_base_with_retry(self):
        rsp1 = responses.post(url="https://example.com/", status=429)
        responses.add(rsp1)
        rsp2 = responses.post(url="https://example.com/", status=429)
        responses.add(rsp2)
        rsp3 = responses.post(url="https://example.com/", status=200)
        responses.add(rsp3)
        base_client = BaseOAuthClientWithRetry(
            max_retries=4,
            backoff_factor=0.1,
            allowed_methods={'POST'}.union(Retry.DEFAULT_ALLOWED_METHODS),
            status_forcelist=Retry.RETRY_AFTER_STATUS_CODES,
        )
        with mock.patch('edx_rest_api_client.client.OAuthAPIClient._ensure_authentication', return_value=True):
            base_client.client.post('https://example.com/')
        assert rsp1.call_count == 1
        assert rsp2.call_count == 1
        assert rsp3.call_count == 1

    def test_plain_base_with_mock_exception(self):
        base_client = BaseOAuthClientWithRetry(
            max_retries=1,
            backoff_factor=0.1,
            allowed_methods={'POST'}.union(Retry.DEFAULT_ALLOWED_METHODS),
            status_forcelist=Retry.RETRY_AFTER_STATUS_CODES,
        )
        with self.assertRaises(requests.exceptions.ConnectionError) as excinfo:
            with mock.patch(
                'edx_rest_api_client.client.OAuthAPIClient._ensure_authentication',
                return_value=True,
            ):
                with mock.patch(
                    'urllib3.connectionpool.HTTPConnectionPool._make_request',
                    side_effect=ChunkedEncodingError(),
                ):
                    base_client.client.post('https://example.com/')
        assert "Max retries exceeded" in str(excinfo.exception)

    # pylint: disable=unexpected-keyword-arg,no-value-for-parameter
    @responses.activate(registry=responses.registries.OrderedRegistry)
    @override_settings(ENTERPRISE_DISCOVERY_CLIENT_BACKOFF_FACTOR=0.1)
    def test_discovery_client(self):
        rsp1 = responses.post(url="https://example.com/", status=429)
        responses.add(rsp1)
        rsp2 = responses.post(url="https://example.com/", status=429)
        responses.add(rsp2)
        rsp3 = responses.post(url="https://example.com/", status=200)
        responses.add(rsp3)
        disco_client = DiscoveryApiClient()
        with mock.patch('edx_rest_api_client.client.OAuthAPIClient._ensure_authentication', return_value=True):
            disco_client.client.post('https://example.com/')
        assert rsp1.call_count == 1
        assert rsp2.call_count == 1
        assert rsp3.call_count == 1

    @override_settings(ENTERPRISE_DISCOVERY_CLIENT_BACKOFF_FACTOR=0.1)
    def test_discovery_client_with_exception(self):
        disco_client = DiscoveryApiClient()
        with self.assertRaises(requests.exceptions.ConnectionError) as excinfo:
            with mock.patch(
                'edx_rest_api_client.client.OAuthAPIClient._ensure_authentication',
                return_value=True,
            ):
                with mock.patch(
                    'urllib3.connectionpool.HTTPConnectionPool._make_request',
                    side_effect=ChunkedEncodingError(),
                ):
                    disco_client.client.post('https://example.com/')
        assert "Max retries exceeded" in str(excinfo.exception)
