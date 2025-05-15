from unittest import mock

from django.core.management import call_command
from django.test import TestCase


PATH_PREFIX = 'enterprise_catalog.apps.catalog.management.commands.remove_old_temporary_catalog_indices.'


class RemoveOldTemporaryCatalogIndicesCommandTests(TestCase):
    command_name = 'remove_old_temporary_catalog_indices'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

    @mock.patch(PATH_PREFIX + 'remove_old_temporary_catalog_indices_task')
    def test_remove_old_temporary_catalog_indices(self, mock_task):
        """
        Verify that the job spins off the correct number of remove_old_temporary_catalog_indices_task
        """
        call_command(self.command_name)
        mock_task.apply_async.assert_called_once_with(
            kwargs={'force': False, 'dry_run': False, 'min_days_ago': 10, 'max_days_ago': 60}
        )

    @mock.patch(PATH_PREFIX + 'remove_old_temporary_catalog_indices_task')
    def test_remove_old_temporary_catalog_indices_dry_run(self, mock_task):
        """
        Verify that the job spins off the correct number of remove_old_temporary_catalog_indices_task
        """
        call_command(self.command_name, dry_run=True)
        mock_task.apply.assert_called_once_with(
            kwargs={'force': False, 'dry_run': True, 'min_days_ago': 10, 'max_days_ago': 60}
        )
