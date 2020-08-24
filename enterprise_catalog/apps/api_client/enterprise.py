from urllib.parse import urljoin

from django.conf import settings

from enterprise_catalog.apps.api_client.base_oauth import BaseOAuthClient


class EnterpriseApiClient(BaseOAuthClient):
    """
    API client to make calls to edx-enterprise API endpoints.
    """
    ENTERPRISE_API_URL = urljoin(settings.LMS_BASE_URL, '/enterprise/api/v1/')
    CUSTOMER_ENDPOINT = urljoin(ENTERPRISE_API_URL, 'enterprise-customer/')

    def get_enterprise_customer(self, customer_uuid):
        """
        Retrieve an Enterprise Customer record from the edx-enterprise API.

        Arguments:
            customer_uuid: string representation of the customer's uuid

        Returns:
            enterprise_customer: dictionary record for customer with given uuid or
                                 empty dictionary if no customer record found
        """
        query_params = {'uuid': customer_uuid}
        response = self.client.get(
            self.CUSTOMER_ENDPOINT,
            params=query_params
        ).json()
        results = response.get('results', [])
        enterprise_customer = results[0] if results else {}
        return enterprise_customer
