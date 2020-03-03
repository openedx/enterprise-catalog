import mock
from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.api.tasks import update_catalog_metadata_task
from enterprise_catalog.apps.catalog.tests.factories import (
    EnterpriseCatalogFactory,
)


class UpdateContentMetadataCommandTests(TestCase):
    command_name = 'update_content_metadata'

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.update_content_metadata.update_catalog_metadata_task.delay'
    )
    def test_update_content_metadata(self, mock_task):
        """
        Verify that the job creates an update task for every enterprise catalog
        """
        [catalog_a, catalog_b, catalog_c] = EnterpriseCatalogFactory.create_batch(3)
        call_command(self.command_name)

        mock_task.assert_any_call(catalog_uuid=str(catalog_a.uuid))
        mock_task.assert_any_call(catalog_uuid=str(catalog_b.uuid))
        mock_task.assert_any_call(catalog_uuid=str(catalog_c.uuid))
