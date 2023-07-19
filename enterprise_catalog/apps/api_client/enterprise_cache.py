"""
Interface to Enterprise Customer details from edx-enterprise API using a volatile cache.
"""
import logging

from dateutil import parser
from django.conf import settings
from django.core.cache import cache

from .constants import ENTERPRISE_CUSTOMER_CACHE_KEY_TPL
from .enterprise import EnterpriseApiClient


logger = logging.getLogger(__name__)


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

    @property
    def learner_portal_enabled(self):
        """
        Return if Enterprise Customer Learner Portal is enabled OR False if unavailable.
        """
        return self.customer_data.get('enable_learner_portal', False)

    @property
    def slug(self):
        """
        Return Enterprise Customer slug OR empty string if unavailable.
        """
        return self.customer_data.get('slug', '')

    @property
    def last_modified_date(self):
        """
        Return Enterprise Customer last modified datetime or None if unavailable.
        """
        if modified_value := self.customer_data.get('modified', None):
            return parser.parse(modified_value)
        return None


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
        enterprise_client = EnterpriseApiClient()
        customer_data = enterprise_client.get_enterprise_customer(uuid)

        if not isinstance(customer_data, dict):
            # TODO: This check should be removed after verifying that the scenario never happens
            logger.warning('Received unexpected customer_data for enterprise customer %s', uuid)
            customer_data = {}

        cache.set(cache_key, customer_data, settings.ENTERPRISE_CUSTOMER_CACHE_TIMEOUT)

    return customer_data
