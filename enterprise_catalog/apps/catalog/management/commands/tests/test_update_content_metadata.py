import mock
from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.catalog.tests.factories import (
    CatalogQueryFactory,
    EnterpriseCatalogFactory,
)


class UpdateContentMetadataCommandTests(TestCase):
    command_name = 'update_content_metadata'

    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.chord')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_catalog_metadata_task')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_full_content_metadata_task')
    def test_update_content_metadata_for_all_queries(self, mock_full_metadata_task, mock_catalog_task, mock_chord):
        """
        Verify that the job creates an update task for every catalog query
        """
        [catalog_query_a, catalog_query_b, catalog_query_c] = CatalogQueryFactory.create_batch(3)

        enterprise_catalog_a = EnterpriseCatalogFactory(catalog_query=catalog_query_a)
        enterprise_catalog_b = EnterpriseCatalogFactory(catalog_query=catalog_query_b)
        enterprise_catalog_c = EnterpriseCatalogFactory(catalog_query=catalog_query_c)

        call_command(self.command_name)

        mock_chord.assert_called_once_with([
            mock_catalog_task.s(catalog_query_id=catalog_query_a),
            mock_catalog_task.s(catalog_query_id=catalog_query_b),
            mock_catalog_task.s(catalog_query_id=catalog_query_c),
        ])
        mock_full_metadata_task.s.assert_called_once()

    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.chord')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_catalog_metadata_task')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_full_content_metadata_task')
    def test_update_content_metadata_for_filtered_queries(self, mock_full_metadata_task, mock_catalog_task, mock_chord):
        """
        Verify that the job creates an update task for every catalog query that is used by
        at least one enterprise catalog.
        """
        [catalog_query_a, catalog_query_b, catalog_query_c] = CatalogQueryFactory.create_batch(3)

        enterprise_catalog_a = EnterpriseCatalogFactory(catalog_query=catalog_query_a)
        enterprise_catalog_b = EnterpriseCatalogFactory(catalog_query=catalog_query_b)

        call_command(self.command_name)

        mock_chord.assert_called_once_with([
            mock_catalog_task.s(catalog_query_id=catalog_query_a),
            mock_catalog_task.s(catalog_query_id=catalog_query_b),
        ])
        mock_full_metadata_task.s.assert_called_once()
