from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    EnterpriseCatalog,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    CatalogQueryFactory,
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
)


class UpdateContentMetadataCommandTests(TestCase):
    command_name = 'update_content_metadata'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.catalog_query_a = CatalogQueryFactory()
        cls.catalog_query_b = CatalogQueryFactory()
        cls.enterprise_catalog_a = EnterpriseCatalogFactory(catalog_query=cls.catalog_query_a)
        cls.enterprise_catalog_b = EnterpriseCatalogFactory(catalog_query=cls.catalog_query_b)

        ContentMetadataFactory.create_batch(3)

    def tearDown(self):
        super().tearDown()
        # clean up any stale test objects
        ContentMetadata.objects.all().delete()
        EnterpriseCatalog.objects.all().delete()

    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.group')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_catalog_metadata_task')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_full_content_metadata_task')
    def test_update_content_metadata_for_all_queries(self, mock_full_metadata_task, mock_catalog_task, mock_group):
        """
        Verify that the job creates an update task for every catalog query
        """
        call_command(self.command_name)

        mock_group.assert_called_once_with([
            mock_catalog_task.s(catalog_query_id=self.catalog_query_a),
            mock_catalog_task.s(catalog_query_id=self.catalog_query_b),
        ])
        mock_full_metadata_task.si.assert_called_once_with()

    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.group')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_catalog_metadata_task')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_full_content_metadata_task')
    def test_update_content_metadata_for_filtered_queries(self, mock_full_metadata_task, mock_catalog_task, mock_group):
        """
        Verify that the job creates an update task for every catalog query that is used by
        at least one enterprise catalog.
        """
        # Create another catalog query that isn't used by any catalog, so shouldn't be updated
        CatalogQueryFactory()

        call_command(self.command_name)

        mock_group.assert_called_once_with([
            mock_catalog_task.s(catalog_query_id=self.catalog_query_a),
            mock_catalog_task.s(catalog_query_id=self.catalog_query_b),
        ])
        mock_full_metadata_task.si.assert_called_once_with()
