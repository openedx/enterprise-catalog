from unittest import mock
from uuid import uuid4

import ddt
from django.test import TestCase

from ..constants import ENTERPRISE_CUSTOMER_ENDPOINT
from ..enterprise import EnterpriseApiClient


@ddt.ddt
class TestEnterpriseApiClient(TestCase):
    """
    Tests for the edx-enterprise API client.
    """

    @mock.patch('enterprise_catalog.apps.api_client.base_oauth.OAuthAPIClient')
    @ddt.data(
        [],
        [
            {
                # 'uuid' is set within test
                'name': 'Test Enterprise',
                'slug': 'test-enterprise',
                'active': True,
                'enable_learner_portal': True,
            },
        ],
    )
    def test_get_enterprise_customer(self, mock_response_results, mock_api_client):
        """
        Tests get_enterprise_customer when a customer record is or isn't found.
        """
        customer_uuid = uuid4()
        mock_api_client.return_value.get.return_value.json.return_value = {
            "count": len(mock_response_results),
            'results': mock_response_results,
            "num_pages": 1,
            "next": None,
            "previous": None,
            "current_page": 1,
            "start": 0,
        }
        if mock_response_results:
            mock_response_results[0]['uuid'] = customer_uuid

        client = EnterpriseApiClient()
        customer_data = client.get_enterprise_customer(customer_uuid)

        mock_api_client.return_value.get.assert_called_with(
            ENTERPRISE_CUSTOMER_ENDPOINT,
            params={'uuid': customer_uuid}
        )
        if mock_response_results:
            self.assertEqual(customer_data, mock_response_results[0])
        else:
            self.assertEqual(customer_data, {})
