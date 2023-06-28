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

    @mock.patch(PATH_PREFIX + 'index_enterprise_catalog_in_algolia_task')
    @mock.patch('enterprise_catalog.apps.catalog.models.CatalogUpdateCommandConfig')
    def test_reindex_algolia(self, mock_command_config, mock_task):
        """
        Verify that the job spins off the correct number of index_enterprise_catalog_in_algolia_task
        """
        mock_command_config.current_options.return_value = {
            'force': False,
            'no_async': False,
        }
        call_command(self.command_name)
        mock_task.apply_async.return_value.get.assert_called_once_with()
