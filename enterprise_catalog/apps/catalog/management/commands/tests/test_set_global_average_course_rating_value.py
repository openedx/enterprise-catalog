from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.api_client.constants import (
    DISCOVERY_AVERAGE_COURSE_REVIEW_CACHE_KEY,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


class TestSetGlobalAverageCourseRatingValue(TestCase):
    command_name = 'set_global_average_course_rating_value'

    @mock.patch('enterprise_catalog.apps.catalog.algolia_utils.cache')
    def test_command_averages_course_reviews(
        self, mock_cache,
    ):
        """
        Verify that the command sifts over content metadata and calculates the
        average review score, setting the value to py-cache.
        """
        ContentMetadataFactory(
            content_type='course',
            json_metadata={'avg_course_rating': 5, 'reviews_count': 20}
        )
        ContentMetadataFactory(
            content_type='course',
            json_metadata={'avg_course_rating': 4, 'reviews_count': 10}
        )
        ContentMetadataFactory(json_metadata={})
        call_command(self.command_name)
        expected_total_average = ((5 * 20) + (4 * 10)) / 30

        mock_cache.set.assert_called_with(
            DISCOVERY_AVERAGE_COURSE_REVIEW_CACHE_KEY,
            expected_total_average,
        )

    @mock.patch('enterprise_catalog.apps.catalog.algolia_utils.cache')
    def test_command_handles_no_course_reviews(
        self, mock_cache,
    ):
        """
        Verify that the job will not blow up if there are no reviews to average.
        """
        call_command(self.command_name)
        mock_cache.set.assert_not_called()
