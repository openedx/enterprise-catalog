from .base_oauth import BaseOAuthClient
from .constants import ENTERPRISE_CUSTOMER_ENDPOINT


class EnterpriseApiClient(BaseOAuthClient):
    """
    API client to make calls to edx-enterprise API endpoints.
    """

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
            ENTERPRISE_CUSTOMER_ENDPOINT,
            params=query_params
        ).json()
        results = response.get('results', [])
        enterprise_customer = results[0] if results else {}
        return enterprise_customer
