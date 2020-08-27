"""
Interface to Enterprise Customer details from edx-enterprise API using a volatile cache.
"""
from django.conf import settings
from django.core.cache import cache

from enterprise_catalog.apps.api_client.enterprise import EnterpriseApiClient

from .constants import ENTERPRISE_CUSTOMER_CACHE_KEY_TPL


class EnterpriseCustomerDetails:
    """
    Details about an Enterprise Customer from the edx-enterprise API.

    Data is cached for 'settings.ENTERPRISE_CUSTOMER_CACHE_TIMEOUT' seconds.
    """

    def __init__(self, uuid):
        """
        Initialize an Enterprise Customer details instance and load data from
        cache or by using the Enterprise API client.

        Arguments:
            uuid (str): Unique identifier for the Enterprise Customer
        """
        self.uuid = uuid
        self.customer_data = _get_enterprise_customer_data(uuid)


def _get_enterprise_customer_data(uuid):
    """
    Retrieve JSON data containing Enterprise Customer details for given uuid.
    Look in cache first, make call to Enterprise API Client if not found.

    Arguments:
        uuid (str): UUID of the Enterprise Customer

    Returns:
        customer_data (dict): Enterprise Customer details OR
            Empty dictionary if no data found in cache or from API.
    """
    cache_key = ENTERPRISE_CUSTOMER_CACHE_KEY_TPL.format(uuid=uuid)
    customer_data = cache.get(cache_key)
    if not isinstance(customer_data, dict):
        client = EnterpriseApiClient()
        customer_data = client.get_enterprise_customer(uuid)
        if not isinstance(customer_data, dict):
            customer_data = {}
        cache.set(cache_key, customer_data, settings.ENTERPRISE_CUSTOMER_CACHE_TIMEOUT)
    return customer_data
