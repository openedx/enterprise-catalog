from unittest import mock

from django.core.management import call_command
from django.test import TestCase


class UpdateFullContentMetadataCommandTests(TestCase):
    command_name = 'update_full_content_metadata'

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.update_full_content_metadata.update_full_content_metadata_task'
    )
    def test_update_full_content_metadata(self, mock_task):
        """
        Verify that the job spins off the update_full_content_metadata_task
        """
        call_command(self.command_name)
        mock_task.delay.assert_called_once()
