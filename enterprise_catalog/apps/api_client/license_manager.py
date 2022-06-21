import logging

from .base_oauth import BaseOAuthClient
from .constants import CUSTOMER_AGREEMENT_ENDPOINT


logger = logging.getLogger(__name__)


class LicenseManagerApiClient(BaseOAuthClient):
    """
    API client to make calls to license-manager API endpoints.
    """

    def get_customer_agreement(
        self,
        enterprise_customer_uuid
    ):
        """
        Returns the customer agreement record for the given enterprise from the license-manager API if it exists.

        Arguments:
            enterprise_customer_uuid: string representation of the customer's uuid

        Returns:
            A dictionary containing details of a customer agreement if it exists, else None

        """

        query_params = {
            'enterprise_customer_uuid': enterprise_customer_uuid
        }

        response = self.client.get(CUSTOMER_AGREEMENT_ENDPOINT, params=query_params)
        response.raise_for_status()
        results = response.json()['results']

        if results:
            return results[0]

        return None
