from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    ContentMetadata,
    EnterpriseCatalog,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    CatalogQueryFactory,
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
)


class CompareCatalogQueriesToFiltersCommandTests(TestCase):
    command_name = 'compare_catalog_queries_to_filters'

    def setUp(self):
        super().setUp()
        self.catalog_query_c = CatalogQueryFactory(content_filter={'content_type': 'course'})
        self.enterprise_catalog_c = EnterpriseCatalogFactory(catalog_query=self.catalog_query_c)
        self.course_c = ContentMetadataFactory.create(content_type='course')
        self.course_c.catalog_queries.add(self.catalog_query_c)

    def tearDown(self):
        super().tearDown()
        # clean up any stale test objects
        ContentMetadata.objects.all().delete()
        CatalogQuery.objects.all().delete()
        EnterpriseCatalog.objects.all().delete()

    @mock.patch('enterprise_catalog.apps.catalog.filters.does_query_match_content')
    def test_update_content_metadata_for_all_queries(
        self, mock_does_query_match_content,
    ):
        """
        Verify that the job calls the comparison with the test data
        """
        mock_does_query_match_content.return_value = True
        call_command(self.command_name)
        mock_does_query_match_content.assert_called_with(self.catalog_query_c.content_filter, self.course_c.json_metadata)
