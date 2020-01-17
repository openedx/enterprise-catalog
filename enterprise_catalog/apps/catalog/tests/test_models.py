""" Tests for catalog models. """

import mock
from django.test import TestCase

from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    update_contentmetadata_from_discovery,
)
from enterprise_catalog.apps.catalog.tests import factories


class TestModels(TestCase):
    """ Models tests. """

    @mock.patch('enterprise_catalog.apps.catalog.models.DiscoveryApiClient')
    def test_contentmetadata_update_from_discovery(self, mock_client):
        """
        update_contentmetadata_from_discovery should update or create
        ContentMetadata Objects from the discovery service api call/
        """
        mock_client.return_value.get_metadata_by_query.return_value = {
            'count': 3,
            'previous': None,
            'next': None,
            'results': [
                {
                    'key': 'course-v1:my+course+1',
                    'title': 'course 1',
                },
                {
                    'key': 'course-v1:my+course+2',
                    'title': 'course 2',
                },
                {
                    'key': 'course-v1:my+course+3',
                    'title': 'course 3',
                },
            ]
        }
        catalog = factories.EnterpriseCatalogFactory()

        assert ContentMetadata.objects.count() == 0
        update_contentmetadata_from_discovery(catalog.uuid)
        mock_client.assert_called_once()
        assert ContentMetadata.objects.count() == 3
