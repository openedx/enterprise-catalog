import mock
from django.core.management import call_command
from django.test import TestCase


class ReindexAlgoliaCommandTests(TestCase):
    command_name = 'reindex_algolia'

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.reindex_algolia.index_enterprise_catalog_courses_in_algolia_task'
    )
    def test_reindex_algolia(self, mock_task):
        """
        Verify that the job spins off the index_enterprise_catalog_courses_in_algolia_task
        """
        call_command(self.command_name)
        mock_task.delay.assert_called_once()
