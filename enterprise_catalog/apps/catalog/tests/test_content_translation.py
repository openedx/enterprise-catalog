"""
Tests for ContentTranslation model and translation utilities.
"""
from django.test import TestCase

from enterprise_catalog.apps.catalog.models import ContentTranslation
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)
from enterprise_catalog.apps.catalog.utils import compute_source_hash


class ContentTranslationModelTests(TestCase):
    """
    Tests for the ContentTranslation model.
    """

    def setUp(self):
        """Set up test data."""
        self.content_metadata = ContentMetadataFactory(
            content_type='course',
            content_key='test-course-key',
            json_metadata={
                'title': 'Test Course',
                'short_description': 'A test course description',
                'full_description': 'Full description of the test course',
                'outcome': 'Learning outcomes',
                'prerequisites': 'Prerequisites for the course',
                'subtitle': 'Course subtitle'
            }
        )

    def test_create_translation(self):
        """Test creating a translation."""
        translation = ContentTranslation.objects.create(
            content_metadata=self.content_metadata,
            language_code='es',
            title='Curso de Prueba',
            short_description='Una descripción del curso de prueba',
            full_description='Descripción completa del curso de prueba',
            outcome='Resultados de aprendizaje',
            prerequisites='Requisitos previos para el curso',
            subtitle='Subtítulo del curso',
            source_hash='test_hash_123'
        )

        self.assertEqual(translation.content_metadata, self.content_metadata)
        self.assertEqual(translation.language_code, 'es')
        self.assertEqual(translation.title, 'Curso de Prueba')
        self.assertEqual(translation.source_hash, 'test_hash_123')

    def test_translation_unique_together(self):
        """Test that content_metadata + language_code combination is unique."""
        ContentTranslation.objects.create(
            content_metadata=self.content_metadata,
            language_code='es',
            title='First Translation',
            source_hash='hash1'
        )

        # Creating another translation for the same content + language should fail
        with self.assertRaises(Exception):
            ContentTranslation.objects.create(
                content_metadata=self.content_metadata,
                language_code='es',
                title='Second Translation',
                source_hash='hash2'
            )

    def test_translation_related_name(self):
        """Test accessing translations via related name."""
        translation = ContentTranslation.objects.create(
            content_metadata=self.content_metadata,
            language_code='es',
            title='Spanish Title',
            source_hash='hash'
        )

        # Access via related name
        self.assertEqual(self.content_metadata.translations.count(), 1)
        self.assertEqual(self.content_metadata.translations.first(), translation)

    def test_translation_str_representation(self):
        """Test string representation of translation."""
        translation = ContentTranslation.objects.create(
            content_metadata=self.content_metadata,
            language_code='es',
            title='Test',
            source_hash='hash'
        )

        expected_str = f"<ContentTranslation: {self.content_metadata.content_key} - es>"
        self.assertEqual(str(translation), expected_str)

    def test_translation_cascade_delete(self):
        """Test that translations are deleted when content_metadata is deleted."""
        ContentTranslation.objects.create(
            content_metadata=self.content_metadata,
            language_code='es',
            title='Test',
            source_hash='hash'
        )

        self.assertEqual(ContentTranslation.objects.count(), 1)

        # Delete the content metadata
        self.content_metadata.delete()

        # Translation should also be deleted
        self.assertEqual(ContentTranslation.objects.count(), 0)

    def test_multiple_languages(self):
        """Test creating translations for multiple languages."""
        ContentTranslation.objects.create(
            content_metadata=self.content_metadata,
            language_code='es',
            title='Spanish Title',
            source_hash='hash1'
        )

        ContentTranslation.objects.create(
            content_metadata=self.content_metadata,
            language_code='fr',
            title='French Title',
            source_hash='hash2'
        )

        self.assertEqual(self.content_metadata.translations.count(), 2)
        self.assertTrue(
            self.content_metadata.translations.filter(language_code='es').exists()
        )
        self.assertTrue(
            self.content_metadata.translations.filter(language_code='fr').exists()
        )


class ComputeSourceHashTests(TestCase):
    """
    Tests for the compute_source_hash utility function.
    """

    def test_compute_source_hash_basic(self):
        """Test computing hash with basic content."""
        content = ContentMetadataFactory(
            json_metadata={
                'title': 'Test Course',
                'short_description': 'Description',
                'full_description': 'Full desc',
                'outcome': 'Outcomes',
                'prerequisites': 'Prereqs',
                'subtitle': 'Subtitle'
            }
        )

        hash_value = compute_source_hash(content)

        # Hash should be a 64-character hex string (SHA256)
        self.assertEqual(len(hash_value), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in hash_value))

    def test_compute_source_hash_consistency(self):
        """Test that same content produces same hash."""
        json_metadata = {
            'title': 'Test Course',
            'short_description': 'Description',
            'full_description': 'Full desc',
            'outcome': 'Outcomes',
            'prerequisites': 'Prereqs',
            'subtitle': 'Subtitle'
        }

        content1 = ContentMetadataFactory(json_metadata=json_metadata.copy())
        content2 = ContentMetadataFactory(json_metadata=json_metadata.copy())

        hash1 = compute_source_hash(content1)
        hash2 = compute_source_hash(content2)

        self.assertEqual(hash1, hash2)

    def test_compute_source_hash_different_content(self):
        """Test that different content produces different hashes."""
        content1 = ContentMetadataFactory(
            json_metadata={'title': 'Course 1', 'short_description': 'Desc 1'}
        )
        content2 = ContentMetadataFactory(
            json_metadata={'title': 'Course 2', 'short_description': 'Desc 2'}
        )

        hash1 = compute_source_hash(content1)
        hash2 = compute_source_hash(content2)

        self.assertNotEqual(hash1, hash2)

    def test_compute_source_hash_missing_fields(self):
        """Test hash computation with missing translatable fields."""
        content = ContentMetadataFactory(
            json_metadata={
                'title': 'Test Course',
                # Missing other fields
            }
        )

        hash_value = compute_source_hash(content)

        # Should still produce a valid hash
        self.assertEqual(len(hash_value), 64)

    def test_compute_source_hash_custom_fields(self):
        """Test hash computation with custom field list."""
        content = ContentMetadataFactory(
            json_metadata={
                'title': 'Test Course',
                'short_description': 'Description',
                'custom_field': 'Custom value'
            }
        )

        # Compute hash with only title
        hash1 = compute_source_hash(content, fields=['title'])

        # Compute hash with title and short_description
        hash2 = compute_source_hash(content, fields=['title', 'short_description'])

        # Hashes should be different
        self.assertNotEqual(hash1, hash2)

    def test_compute_source_hash_empty_values(self):
        """Test hash computation with empty string values."""
        content = ContentMetadataFactory(
            json_metadata={
                'title': '',
                'short_description': '',
                'full_description': 'Some content'
            }
        )

        hash_value = compute_source_hash(content)

        # Should produce a valid hash even with empty values
        self.assertEqual(len(hash_value), 64)
