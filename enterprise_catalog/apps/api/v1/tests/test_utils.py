from datetime import timedelta

from django.test import TestCase

from enterprise_catalog.apps.api.v1.utils import (
    get_archived_content_count,
    get_most_recent_modified_time,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)
from enterprise_catalog.apps.catalog.utils import localized_utcnow
from enterprise_catalog.apps.curation.tests.factories import (
    HighlightedContentFactory,
)


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

    def test_get_archived_content_count(self):
        """
        Test that archived content will increment the count.
        """
        content_1 = ContentMetadataFactory.create(_json_metadata={'course_run_statuses': ['archived']})
        content_2 = ContentMetadataFactory.create(_json_metadata={'course_run_statuses': ['unpublished', 'archived']})
        # if there's at least one published course run, the content should not be considered archived
        content_3 = ContentMetadataFactory.create(_json_metadata={'course_run_statuses': ['published', 'archived']})

        highlighted_content_1 = HighlightedContentFactory(content_metadata=content_1)
        highlighted_content_2 = HighlightedContentFactory(content_metadata=content_2)
        highlighted_content_3 = HighlightedContentFactory(content_metadata=content_3)

        archived_content_count = get_archived_content_count(
            [highlighted_content_1, highlighted_content_2, highlighted_content_3]
        )
        assert archived_content_count == 2
