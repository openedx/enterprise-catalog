from datetime import timedelta

from django.test import TestCase

from enterprise_catalog.apps.api.v1.utils import get_most_recent_modified_time
from enterprise_catalog.apps.catalog.utils import localized_utcnow


class ApiUtilsTests(TestCase):
    """
    Tests for the Enterprise Catalog API client utils
    """

    def test_get_most_recent_modified_time_catalog_modified(self):
        """
        Test that the get_most_recent_modified_time function will account for catalog modified times
        """
        now = localized_utcnow()
        catalog_time = now
        customer_time = now - timedelta(hours=1)
        content_time = now - timedelta(hours=1)
        most_recent_time = get_most_recent_modified_time(content_time, catalog_time, customer_time)
        assert most_recent_time == catalog_time

    def test_get_most_recent_modified_time_customer_modified(self):
        """
        Test that the get_most_recent_modified_time function will account for customer modified times
        """
        now = localized_utcnow()
        customer_time = now
        catalog_time = now - timedelta(hours=1)
        content_time = now - timedelta(hours=1)
        most_recent_time = get_most_recent_modified_time(content_time, catalog_time, customer_time)
        assert most_recent_time == customer_time

    def test_get_most_recent_modified_time_content_modified(self):
        """
        Test that the get_most_recent_modified_time function will account for content modified times
        """
        now = localized_utcnow()
        content_time = now
        catalog_time = now - timedelta(hours=1)
        customer_time = now - timedelta(hours=1)
        most_recent_time = get_most_recent_modified_time(content_time, catalog_time, customer_time)
        assert most_recent_time == content_time

    def test_get_most_recent_modified_time_accounts_for_no_customer_modified(self):
        """
        Test that the get_most_recent_modified_time function will account for content modified times when customer
        modified times do not exist
        """
        now = localized_utcnow()
        content_time = now
        catalog_time = now - timedelta(hours=1)
        customer_time = None
        most_recent_time = get_most_recent_modified_time(content_time, catalog_time, customer_time)
        assert most_recent_time == content_time
