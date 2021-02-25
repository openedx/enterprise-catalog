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

    @mock.patch(PATH_PREFIX + 'index_enterprise_catalog_courses_in_algolia_task')
    def test_reindex_algolia(self, mock_task):
        """
        Verify that the job spins off the correct number of index_enterprise_catalog_courses_in_algolia_task
        """
        call_command(self.command_name)
        mock_task.apply_async.return_value.get.assert_called_once_with()
