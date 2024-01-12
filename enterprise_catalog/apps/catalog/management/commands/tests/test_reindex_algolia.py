from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


PATH_PREFIX = 'enterprise_catalog.apps.catalog.management.commands.reindex_algolia.'


class ReindexAlgoliaCommandTests(TestCase):
    command_name = 'reindex_algolia'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.content_metadata = ContentMetadataFactory.create_batch(3, content_type=COURSE)

    @mock.patch(PATH_PREFIX + 'index_enterprise_catalog_in_algolia_task')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.reindex_algolia.CatalogUpdateCommandConfig')
    def test_reindex_algolia(self, mock_command_config, mock_task):
        """
        Verify that the job spins off the correct number of index_enterprise_catalog_in_algolia_task
        """
        mock_command_config.current_options.return_value = {
            'force': False,
            'no_async': False,
        }
        call_command(self.command_name)
        mock_task.apply_async.assert_called_once_with(kwargs={'force': False, 'dry_run': False})
        mock_task.apply_async.return_value.get.assert_called_once_with()

    @mock.patch(PATH_PREFIX + 'index_enterprise_catalog_in_algolia_task')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.reindex_algolia.CatalogUpdateCommandConfig')
    def test_reindex_algolia_no_async(self, mock_command_config, mock_task):
        """
        Verify that the job spins off the correct number of index_enterprise_catalog_in_algolia_task
        """
        mock_command_config.current_options.return_value = {
            'force': False,
            'no_async': True,
        }
        call_command(self.command_name)
        mock_task.apply.assert_called_once_with(kwargs={'force': False, 'dry_run': False})  # force=False, dry_run=False
        mock_task.apply_async.assert_not_called()

    @mock.patch(PATH_PREFIX + 'index_enterprise_catalog_in_algolia_task')
    @mock.patch('enterprise_catalog.apps.catalog.management.commands.reindex_algolia.CatalogUpdateCommandConfig')
    def test_reindex_algolia_dry_run(self, mock_command_config, mock_task):
        """
        Verify that the job spins off the correct number of index_enterprise_catalog_in_algolia_task
        """
        mock_command_config.current_options.return_value = {
            'force': False,
            'no_async': False,
        }
        call_command(self.command_name, dry_run=True)
        mock_task.apply_async.assert_called_once_with(kwargs={'force': False, 'dry_run': True})
        mock_task.apply_async.return_value.get.assert_called_once_with()
