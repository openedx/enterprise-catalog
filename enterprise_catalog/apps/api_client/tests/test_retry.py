""" Tests for EnterpriseRery and BaseOAuthClientWithRetry """
from django.test import TestCase
from requests.exceptions import ChunkedEncodingError
from urllib3.exceptions import ProtocolError

from ..base_oauth_with_retry import EnterpriseRetry


class TestEnterpriseRetry(TestCase):
    """ EnterpriseRetry tests. """

    def test_existing_protocol_error_handling(self):
        """
        Ensure the parent class logic still works
        """
        # pylint: disable=protected-access
        assert EnterpriseRetry()._is_read_error(ProtocolError())

    def test_existing_negative_case(self):
        """
        Ensure the parent class logic still works
        """
        # pylint: disable=protected-access
        assert EnterpriseRetry()._is_read_error(Exception()) is False

    def test_requests_chuncked_error(self):
        """
        Ensure the added Exception(s) are working
        """
        # pylint: disable=protected-access
        assert EnterpriseRetry()._is_read_error(ChunkedEncodingError())
