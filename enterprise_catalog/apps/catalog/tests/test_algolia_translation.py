from django.test import TestCase

from enterprise_catalog.apps.api.tasks import add_metadata_to_algolia_objects
from enterprise_catalog.apps.catalog.algolia_utils import (
    create_spanish_algolia_object,
)
from enterprise_catalog.apps.catalog.models import ContentTranslation
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


class AlgoliaTranslationTests(TestCase):
    def test_create_spanish_algolia_object_no_translation(self):
        """
        Test that create_spanish_algolia_object returns None when no translation exists.
        """
        original_object = {'objectID': 'course-123'}
        content_metadata = ContentMetadataFactory(content_type='course', content_key='course-123')

        result = create_spanish_algolia_object(original_object, content_metadata)
        self.assertIsNone(result)

    def test_create_spanish_algolia_object_with_translation(self):
        """
        Test that create_spanish_algolia_object returns translated object when translation exists.
        """
        original_object = {
            'objectID': 'course-123',
            'title': 'Original Title',
            'short_description': 'Original Description',
            'full_description': 'Original Full',
            'subtitle': 'Original Subtitle'
        }
        content_metadata = ContentMetadataFactory(content_type='course', content_key='course-123')
        ContentTranslation.objects.create(
            content_metadata=content_metadata,
            language_code='es',
            title='Título Español',
            short_description='Descripción Español',
            full_description='Descripción Completa Español',
            subtitle='Subtítulo Español'
        )

        result = create_spanish_algolia_object(original_object, content_metadata)

        self.assertIsNotNone(result)
        self.assertEqual(result['objectID'], 'course-123-es')
        self.assertEqual(result['title'], 'Título Español')
        self.assertEqual(result['short_description'], 'Descripción Español')
        self.assertEqual(result['full_description'], 'Descripción Completa Español')
        self.assertEqual(result['subtitle'], 'Subtítulo Español')
        self.assertEqual(result['language'], 'es')

    def test_add_metadata_to_algolia_objects_creates_spanish_version(self):
        """
        Test that add_metadata_to_algolia_objects creates Spanish objects when translation exists.
        """
        metadata = ContentMetadataFactory(content_type='course')
        ContentTranslation.objects.create(
            content_metadata=metadata,
            language_code='es',
            title='Título Español'
        )

        algolia_products = {}
        catalog_uuids = ['cat-1']
        customer_uuids = ['cust-1']
        catalog_queries = [('query-1', 'Query Title')]
        academy_uuids = []
        academy_tags = []
        video_ids = []

        add_metadata_to_algolia_objects(
            metadata,
            algolia_products,
            catalog_uuids,
            customer_uuids,
            catalog_queries,
            academy_uuids,
            academy_tags,
            video_ids
        )

        # Check for Spanish objects
        spanish_keys = [k for k in algolia_products.keys() if '-es' in k]
        self.assertGreater(len(spanish_keys), 0)

        # Verify one of the Spanish objects
        spanish_obj = algolia_products[spanish_keys[0]]
        self.assertEqual(spanish_obj['title'], 'Título Español')
        self.assertIn('-es', spanish_obj['objectID'])

    def test_add_metadata_to_algolia_objects_skips_spanish_version(self):
        """
        Test that add_metadata_to_algolia_objects skips Spanish objects when no translation exists.
        """
        metadata = ContentMetadataFactory(content_type='course')
        # No translation created

        algolia_products = {}
        catalog_uuids = ['cat-1']
        customer_uuids = ['cust-1']
        catalog_queries = [('query-1', 'Query Title')]
        academy_uuids = []
        academy_tags = []
        video_ids = []

        add_metadata_to_algolia_objects(
            metadata,
            algolia_products,
            catalog_uuids,
            customer_uuids,
            catalog_queries,
            academy_uuids,
            academy_tags,
            video_ids
        )

        # Check for Spanish objects - should be none
        spanish_keys = [k for k in algolia_products.keys() if '-es' in k]
        self.assertEqual(len(spanish_keys), 0)

        # Check for English objects - should exist
        english_keys = [k for k in algolia_products.keys() if not k.endswith('-es') and 'catalog-uuids' in k]
        self.assertGreater(len(english_keys), 0)
