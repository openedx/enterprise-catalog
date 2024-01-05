""" Tests for catalog query filtering. """
import logging

import ddt
from django.test import TestCase

from enterprise_catalog.apps.catalog.algolia_content_indexing import (
    get_catalogs_for_content,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    CatalogQueryFactory,
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
)


logger = logging.getLogger(__name__)


@ddt.ddt
class AlgoliaContentIndexingTests(TestCase):
    """ Tests for catalog query filtering. """

    def test_does_content_belong_in_catalog(self):
        """ Test that `get_catalogs_for_content_metadata` matches content to correct catalog. """
        content_metadata = ContentMetadataFactory(content_type='course')
        content_key = content_metadata.json_metadata.get('key')
        status = content_metadata.json_metadata.get('status')

        included_query = CatalogQueryFactory(
            content_filter={'content_type': 'course', 'status': status, 'key': content_key}
        )
        excluded_query = CatalogQueryFactory(
            content_filter={'content_type': 'course', 'status': status, 'key__exclude': [content_key]}
        )
        included_catalog = EnterpriseCatalogFactory(
            catalog_query=included_query
        )
        EnterpriseCatalogFactory(
            catalog_query=excluded_query
        )
        found_catalogs = get_catalogs_for_content(content_key)
        assert len(found_catalogs) == 1
        assert found_catalogs[0] == included_catalog
