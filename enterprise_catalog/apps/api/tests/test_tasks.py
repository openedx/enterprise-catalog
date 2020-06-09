"""
Tests for the enterprise_catalog API celery tasks
"""
from unittest import mock

from django.test import TestCase

from enterprise_catalog.apps.api import tasks
from enterprise_catalog.apps.catalog.tests.factories import CatalogQueryFactory


class EnterpriseCatalogCeleryTaskTests(TestCase):
    def setUp(self):
        super(EnterpriseCatalogCeleryTaskTests, self).setUp()
        self.catalog_query = CatalogQueryFactory()

    @mock.patch('enterprise_catalog.apps.api.tasks.update_contentmetadata_from_discovery')
    def test_refresh_metadata(self, update_contentmetadata_from_discovery_mock):
        tasks.update_catalog_metadata_task(self.catalog_query.id)
        update_contentmetadata_from_discovery_mock.assert_called_with(self.catalog_query.id)
