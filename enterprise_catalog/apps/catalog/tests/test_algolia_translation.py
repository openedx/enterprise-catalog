from unittest import mock

from django.test import TestCase

from enterprise_catalog.apps.api.tasks import add_metadata_to_algolia_objects
from enterprise_catalog.apps.catalog.algolia_utils import (
    create_spanish_algolia_object,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)


class AlgoliaTranslationTests(TestCase):
    def test_create_spanish_algolia_object(self):
        """
        Test that create_spanish_algolia_object correctly translates fields and updates objectID.
        """
        original_object = {
            'objectID': 'course-123',
            'title': 'Introduction to Python',
            'short_description': 'Learn Python basics',
            'full_description': 'A comprehensive guide to Python.',
            'outcome': 'You will know Python.',
            'prerequisites': 'None',
            'subtitle': 'Beginner friendly',
            'aggregation_key': 'course-123',
            'other_field': 'Should not change'
        }

        with mock.patch('enterprise_catalog.apps.ai_curation.utils.open_ai_utils.chat_completions') as mock_chat:
            # Mock translation response
            def side_effect(messages):
                content = messages[0]['content']
                if 'Introduction to Python' in content:
                    return ['Introducción a Python']
                if 'Learn Python basics' in content:
                    return ['Aprende los conceptos básicos de Python']
                return ['Translated text']

            mock_chat.side_effect = side_effect

            spanish_object = create_spanish_algolia_object(original_object)

            self.assertEqual(spanish_object['objectID'], 'course-123-es')
            self.assertEqual(spanish_object['title'], 'Introducción a Python')
            self.assertEqual(spanish_object['short_description'], 'Aprende los conceptos básicos de Python')
            self.assertEqual(spanish_object['other_field'], 'Should not change')
            self.assertEqual(spanish_object['aggregation_key'], 'course-123')

    def test_add_metadata_to_algolia_objects_creates_spanish_version(self):
        """
        Test that add_metadata_to_algolia_objects creates both English and Spanish objects.
        """
        metadata = ContentMetadataFactory(content_type='course')
        algolia_products = {}
        catalog_uuids = ['cat-1']
        customer_uuids = ['cust-1']
        catalog_queries = [('query-1', 'Query Title')]
        academy_uuids = []
        academy_tags = []
        video_ids = []

        with mock.patch('enterprise_catalog.apps.ai_curation.utils.open_ai_utils.chat_completions') as mock_chat:
            mock_chat.return_value = ['Translated Text']

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

            # Check for English objects
            english_keys = [k for k in algolia_products.keys() if not k.endswith('-es') and 'catalog-uuids' in k]
            self.assertTrue(len(english_keys) > 0)

            # Check for Spanish objects
            spanish_keys = [k for k in algolia_products.keys() if '-es-' in k and 'catalog-uuids' in k]
            self.assertTrue(len(spanish_keys) > 0)

            # Verify structure of a Spanish object
            spanish_obj = algolia_products[spanish_keys[0]]
            self.assertIn('-es', spanish_obj['objectID'])
            self.assertEqual(spanish_obj['enterprise_catalog_uuids'], catalog_uuids)
