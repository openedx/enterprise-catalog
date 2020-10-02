import mock
from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.api.tasks import update_catalog_metadata_task
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    EnterpriseCatalog,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    CatalogQueryFactory,
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

    def tearDown(self):
        super(UpdateContentMetadataCommandTests, self).tearDown()
        # clean up any stale test objects
        ContentMetadata.objects.all().delete()
        EnterpriseCatalog.objects.all().delete()

    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.chord')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_catalog_metadata_task')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_full_content_metadata_task')
    def test_update_content_metadata_for_all_queries(self, mock_full_metadata_task, mock_catalog_task, mock_chord):
        """
        Verify that the job creates an update task for every catalog query
        """
        call_command(self.command_name)

        mock_chord.assert_called_once_with([
            mock_catalog_task.s(catalog_query_id=self.catalog_query_a),
            mock_catalog_task.s(catalog_query_id=self.catalog_query_b),
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
        # Create another catalog query that isn't used by any catalog, so shouldn't be updated
        CatalogQueryFactory()

        call_command(self.command_name)

        mock_chord.assert_called_once_with([
            mock_catalog_task.s(catalog_query_id=self.catalog_query_a),
            mock_catalog_task.s(catalog_query_id=self.catalog_query_b),
        ])
        mock_full_metadata_task.s.assert_called_once()

    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.chord')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_catalog_metadata_task')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_full_content_metadata_task')
    def test_update_content_metadata_with_args(self, mock_full_metadata_task, mock_catalog_task, mock_chord):
        """
        Verify that the job only updates the catalog query associated with the provided catalog_uuid if given.
        """
        call_command(self.command_name, catalog_uuids=[self.enterprise_catalog_a.uuid])

        mock_chord.assert_called_once_with([
            mock_catalog_task.s(catalog_query_id=self.catalog_query_a),
        ])
        mock_full_metadata_task.s.assert_called_once()
