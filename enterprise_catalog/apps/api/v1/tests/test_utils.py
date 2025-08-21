from datetime import timedelta

from django.test import TestCase

from enterprise_catalog.apps.api.v1.utils import (
    get_archived_content_count,
    get_most_recent_modified_time,
    is_course_run_active,
    str_to_bool,
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

    def test_is_course_run_active(self):
        """
        Test that the is_course_run_active function correctly identifies active course runs.
        """
        # Test case where course run is active
        active_course_run = {
            'is_enrollable': True,
            'is_marketable_external': True,
            'status': 'published',
            'is_marketable': True
        }
        assert is_course_run_active(active_course_run) is True

        # Test case where course run is not active due to not being enrollable
        not_enrollable_course_run = {
            'is_enrollable': False,
            'is_marketable_external': True,
            'status': 'published',
            'is_marketable': True
        }
        assert is_course_run_active(not_enrollable_course_run) is False

        # Test case where course is not is_marketable but is_marketable_external
        not_marketable_course_run = {
            'is_enrollable': True,
            'is_marketable_external': True,
            'status': 'published',
            'is_marketable': False
        }
        assert is_course_run_active(not_marketable_course_run) is True

        # Test case where course run is not active due to not being published
        not_published_course_run = {
            'is_enrollable': False,
            'is_marketable_external': False,
            'status': 'archived',
            'is_marketable': True
        }
        assert is_course_run_active(not_published_course_run) is False

        # Test case where course run is active due to being marketable externally
        marketable_external_course_run = {
            'is_enrollable': True,
            'is_marketable_external': True,
            'status': 'reviewed',
            'is_marketable': False
        }
        assert is_course_run_active(marketable_external_course_run) is True

    def test_strtobool(self):
        assert str_to_bool('true') is True
        assert str_to_bool('TRUE') is True
        assert str_to_bool('false') is False
        assert str_to_bool(True) is True
        assert str_to_bool(False) is False
        with self.assertRaises(TypeError) as context:
            str_to_bool('neithertruenorfalse')
        with self.assertRaises(TypeError) as context:
            str_to_bool(0)
        assert isinstance(context.exception.__context__, AttributeError)
