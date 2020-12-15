from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.catalog.models import ContentMetadata
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


class UpdateFullContentMetadataCommandTests(TestCase):
    command_name = 'update_full_content_metadata'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        ContentMetadataFactory.create_batch(3)

    def _get_content_keys(self):
        return [content_metadata.content_key for content_metadata in ContentMetadata.objects.all()]

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.update_full_content_metadata.update_full_content_metadata_task'
    )
    def test_update_full_content_metadata(self, mock_task):
        """
        Verify that the job spins off the update_full_content_metadata_task
        """
        call_command(self.command_name)
        mock_task.run.assert_called_once_with(self._get_content_keys())
