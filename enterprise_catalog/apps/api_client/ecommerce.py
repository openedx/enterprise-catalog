import logging

from .base_oauth import BaseOAuthClient
from .constants import COUPONS_OVERVIEW_ENDPOINT


logger = logging.getLogger(__name__)


class EcommerceApiClient(BaseOAuthClient):
    """
    API client to make calls to ecommerce API endpoints.
    """

    def get_coupons_overview(
        self,
        enterprise_customer_uuid,
        query_params=None
    ):
        """
        Retrieve the coupons overview for the given enterprise from the ecommerce API.

        Arguments:
            enterprise_customer_uuid: string representation of the customer's uuid

        Returns:
            A list of coupons for the enterprise.

        """

        if not query_params:
            query_params = {
                'page': 1,
                'page_size': 50,
                'filter': 'active'
            }

        url = COUPONS_OVERVIEW_ENDPOINT.format(enterprise_customer_uuid=enterprise_customer_uuid)

        response = self.client.get(url, params=query_params)
        response.raise_for_status()
        results = response.json()['results']
        return results
