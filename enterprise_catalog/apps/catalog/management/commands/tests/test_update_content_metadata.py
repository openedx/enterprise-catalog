import mock
from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.api.tasks import update_catalog_metadata_task
from enterprise_catalog.apps.catalog.tests.factories import (
    CatalogQueryFactory,
    EnterpriseCatalogFactory,
)


class UpdateContentMetadataCommandTests(TestCase):
    command_name = 'update_content_metadata'

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_catalog_metadata_task.delay'
    )
    def test_update_content_metadata_for_all_queries(self, mock_task):
        """
        Verify that the job creates an update task for every catalog query
        """
        [catalog_query_a, catalog_query_b, catalog_query_c] = CatalogQueryFactory.create_batch(3)

        enterprise_catalog_a = EnterpriseCatalogFactory(catalog_query=catalog_query_a)
        enterprise_catalog_b = EnterpriseCatalogFactory(catalog_query=catalog_query_b)
        enterprise_catalog_c = EnterpriseCatalogFactory(catalog_query=catalog_query_c)

        call_command(self.command_name)

        assert mock_task.call_count == 3

        mock_task.assert_any_call(catalog_query_id=catalog_query_a.id)
        mock_task.assert_any_call(catalog_query_id=catalog_query_b.id)
        mock_task.assert_any_call(catalog_query_id=catalog_query_c.id)

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_catalog_metadata_task.delay'
    )
    def test_update_content_metadata_for_filtered_queries(self, mock_task):
        """
        Verify that the job creates an update task for every catalog query that is used by
        at least one enterprise catalog.
        """
        [catalog_query_a, catalog_query_b, catalog_query_c] = CatalogQueryFactory.create_batch(3)

        enterprise_catalog_a = EnterpriseCatalogFactory(catalog_query=catalog_query_a)
        enterprise_catalog_b = EnterpriseCatalogFactory(catalog_query=catalog_query_b)

        call_command(self.command_name)

        assert mock_task.call_count == 2

        mock_task.assert_any_call(catalog_query_id=catalog_query_a.id)
        mock_task.assert_any_call(catalog_query_id=catalog_query_b.id)
