"""
Integration tests for Algolia indexing.
"""
from unittest import mock

from django.test import TestCase

from enterprise_catalog.apps.api.tasks import _reindex_algolia
from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.models import ContentTranslation
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


class AlgoliaIntegrationTests(TestCase):
    """
    Integration tests for Algolia indexing logic.
    """

    @mock.patch('enterprise_catalog.apps.api.tasks._retrieve_inactive_tmp_indices')
    @mock.patch('enterprise_catalog.apps.api.tasks._delete_indices')
    @mock.patch('enterprise_catalog.apps.api.tasks.configure_algolia_index')
    @mock.patch('enterprise_catalog.apps.api.tasks.get_initialized_algolia_client')
    def test_algolia_indexing_with_spanish_translation(
        self,
        mock_get_client,
        mock_configure,
        mock_delete,
        mock_retrieve
    ):
        """
        Test that _reindex_algolia pushes double the objects when Spanish translation exists.
        """
        # Setup
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client
        
        # Create a course
        course = ContentMetadataFactory(content_type=COURSE, content_key='course-v1:Test+Course')
        
        # Create catalog query and associate with course
        from enterprise_catalog.apps.catalog.tests.factories import CatalogQueryFactory, EnterpriseCatalogFactory
        catalog_query = CatalogQueryFactory()
        course.catalog_queries.add(catalog_query)
        
        # Create enterprise catalog associated with query
        EnterpriseCatalogFactory(catalog_query=catalog_query)

        content_keys = [course.content_key]

        # --- Execution 1: No Translation ---
        _reindex_algolia(
            indexable_content_keys=content_keys,
            nonindexable_content_keys=[],
            dry_run=False
        )

        # Verify 3 objects pushed (catalog_uuids, customer_uuids, catalog_queries)
        self.assertTrue(mock_client.replace_all_objects.called)
        # Get the generator passed to replace_all_objects
        args, _ = mock_client.replace_all_objects.call_args
        generator = args[0]
        # Consume generator to count objects
        objects = list(generator)
        self.assertEqual(len(objects), 3, "Should have 3 objects (English only)")
        self.assertFalse(any(obj['objectID'].endswith('-es') for obj in objects))

        # Reset mock
        mock_client.reset_mock()

        # --- Execution 2: With Translation ---
        ContentTranslation.objects.create(
            content_metadata=course,
            language_code='es',
            title='Curso de Prueba'
        )

        _reindex_algolia(
            indexable_content_keys=content_keys,
            nonindexable_content_keys=[],
            dry_run=False
        )

        # Verify 6 objects pushed (3 English + 3 Spanish)
        self.assertTrue(mock_client.replace_all_objects.called)
        args, _ = mock_client.replace_all_objects.call_args
        generator = args[0]
        objects = list(generator)
        self.assertEqual(len(objects), 6, "Should have 6 objects (English + Spanish)")
        
        # Verify IDs
        english_obj = next(obj for obj in objects if '-es-' not in obj['objectID'])
        spanish_obj = next(obj for obj in objects if '-es-' in obj['objectID'])
        
        self.assertIsNotNone(english_obj)
        self.assertIsNotNone(spanish_obj)
        self.assertEqual(spanish_obj['title'], 'Curso de Prueba')
