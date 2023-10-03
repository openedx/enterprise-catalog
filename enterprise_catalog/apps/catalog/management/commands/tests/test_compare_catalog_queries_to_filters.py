from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.catalog.tasks import (
    compare_catalog_queries_to_filters_task,
)


class CompareCatalogQueriesToFiltersCommandTests(TestCase):
    command_name = 'compare_catalog_queries_to_filters'

    @mock.patch('enterprise_catalog.apps.catalog.tasks.compare_catalog_queries_to_filters_task')
    def test_update_content_metadata_for_all_queries(
        self, mock_compare_catalog_queries_to_filters_task,
    ):
        """
        Verify that the job calls the comparison with the test data
        """
        call_command(self.command_name)
        compare_catalog_queries_to_filters_task()
        mock_compare_catalog_queries_to_filters_task.s.assert_called_once()
