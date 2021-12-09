from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


class UpdateFullContentMetadataCommandTests(TestCase):
    command_name = 'update_full_content_metadata'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        ContentMetadataFactory.create_batch(3)

    def setUp(self):
        super().setUp()
        self.command_config_mock = mock.patch('enterprise_catalog.apps.catalog.models.CatalogUpdateCommandConfig')
        mock_config = self.command_config_mock.start()
        mock_config.current_config.return_value = {
            'force': False,
            'no_async': False,
        }

    def tearDown(self):
        super().tearDown()
        self.command_config_mock.stop()

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.update_full_content_metadata.update_full_content_metadata_task'
    )
    def test_update_full_content_metadata(self, mock_task):
        """
        Verify that the job spins off the update_full_content_metadata_task
        """
        call_command(self.command_name)
        mock_task.apply_async.return_value.get.assert_called_once_with()
