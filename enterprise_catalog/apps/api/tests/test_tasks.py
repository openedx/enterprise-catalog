"""
Tests for the enterprise_catalog API celery tasks
"""
from unittest import mock

from django.test import TestCase

from enterprise_catalog.apps.api import tasks
from enterprise_catalog.apps.catalog.tests.factories import (
    EnterpriseCatalogFactory,
)


class EnterpriseCatalogCeleryTaskTests(TestCase):
    def setUp(self):
        super(EnterpriseCatalogCeleryTaskTests, self).setUp()
        self.enterprise_catalog = EnterpriseCatalogFactory()

    @mock.patch('enterprise_catalog.apps.api.tasks.update_contentmetadata_from_discovery')
    def test_refresh_metadata(self, update_contentmetadata_from_discovery_mock):
        tasks.update_catalog_metadata_task(self.enterprise_catalog.uuid)  # pylint: disable=no-value-for-parameter
        update_contentmetadata_from_discovery_mock.assert_called_with(self.enterprise_catalog.uuid)
