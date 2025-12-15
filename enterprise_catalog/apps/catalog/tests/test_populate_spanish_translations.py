"""
Tests for populate_spanish_translations management command.
"""
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from enterprise_catalog.apps.catalog.models import ContentTranslation
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)
from enterprise_catalog.apps.catalog.utils import compute_source_hash


class PopulateSpanishTranslationsCommandTests(TestCase):
    """
    Tests for the populate_spanish_translations management command.
    """

    def setUp(self):
        """Set up test data."""
        self.content1 = ContentMetadataFactory(
            content_key='course-1',
            content_type='course',
            json_metadata={
                'title': 'Introduction to Python',
                'short_description': 'Learn Python basics',
                'full_description': 'A comprehensive course on Python fundamentals',
            }
        )
        self.content2 = ContentMetadataFactory(
            content_key='course-2',
            content_type='course',
            json_metadata={
                'title': 'Advanced JavaScript',
                'short_description': 'Master JavaScript',
            }
        )

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.'
        'populate_spanish_translations.translate_object_fields'
    )
    def test_command_creates_translations(self, mock_translate):
        """Test that command creates new translations."""
        mock_translate.return_value = {
            'title': 'Título traducido',
            'short_description': 'Descripción corta',
        }

        # Run command
        call_command('populate_spanish_translations')

        # Check translations were created
        self.assertEqual(ContentTranslation.objects.count(), 2)

        translation1 = ContentTranslation.objects.get(content_metadata=self.content1)
        self.assertEqual(translation1.language_code, 'es')
        self.assertEqual(translation1.title, 'Título traducido')
        self.assertIsNotNone(translation1.source_hash)

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.'
        'populate_spanish_translations.translate_object_fields'
    )
    def test_command_skips_existing_translations(self, mock_translate):
        """Test that command skips translations with matching hash."""
        mock_translate.return_value = {'title': 'Translated'}

        # Create existing translation with correct hash
        source_hash = compute_source_hash(self.content1)
        ContentTranslation.objects.create(
            content_metadata=self.content1,
            language_code='es',
            title='Existing Translation',
            source_hash=source_hash
        )

        # Run command
        call_command('populate_spanish_translations')

        # Should not update existing translation
        translation = ContentTranslation.objects.get(content_metadata=self.content1)
        self.assertEqual(translation.title, 'Existing Translation')

        # Should create translation for content2
        self.assertEqual(ContentTranslation.objects.count(), 2)

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.'
        'populate_spanish_translations.translate_object_fields'
    )
    def test_command_force_retranslate(self, mock_translate):
        """Test that --force flag re-translates existing content."""
        mock_translate.return_value = {'title': 'New Translation'}

        # Create existing translation
        ContentTranslation.objects.create(
            content_metadata=self.content1,
            language_code='es',
            title='Old Translation',
            source_hash='old_hash'
        )

        # Run command with force
        call_command('populate_spanish_translations', force=True)

        # Should update existing translation
        translation = ContentTranslation.objects.get(content_metadata=self.content1)
        self.assertEqual(translation.title, 'New Translation')

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.'
        'populate_spanish_translations.translate_object_fields'
    )
    def test_command_content_keys_filter(self, mock_translate):
        """Test filtering by content keys."""
        mock_translate.return_value = {'title': 'Translated'}

        # Run command for only content1
        call_command('populate_spanish_translations', content_keys=['course-1'])

        # Should only create translation for content1
        self.assertEqual(ContentTranslation.objects.count(), 1)
        self.assertTrue(
            ContentTranslation.objects.filter(content_metadata=self.content1).exists()
        )
        self.assertFalse(
            ContentTranslation.objects.filter(content_metadata=self.content2).exists()
        )

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.'
        'populate_spanish_translations.translate_object_fields'
    )
    def test_command_dry_run(self, mock_translate):
        """Test that--dry-run doesn't save translations."""
        mock_translate.return_value = {'title': 'Translated'}

        # Run command in dry-run mode
        call_command('populate_spanish_translations', dry_run=True)

        # No translations should be saved
        self.assertEqual(ContentTranslation.objects.count(), 0)

        # But translate should still be called
        self.assertTrue(mock_translate.called)

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.'
        'populate_spanish_translations.translate_object_fields'
    )
    def test_command_updates_stale_translations(self, mock_translate):
        """Test that command updates translations when content changes."""
        mock_translate.return_value = {'title': 'Updated Translation'}

        # Create translation with old hash
        ContentTranslation.objects.create(
            content_metadata=self.content1,
            language_code='es',
            title='Old Translation',
            source_hash='outdated_hash'  # Different from current content
        )

        # Run command (without force)
        call_command('populate_spanish_translations')

        # Should update the translation because hash doesn't match
        translation = ContentTranslation.objects.get(content_metadata=self.content1)
        self.assertEqual(translation.title, 'Updated Translation')

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.'
        'populate_spanish_translations.translate_object_fields'
    )
    def test_command_batch_processing(self, mock_translate):
        """Test command processes in batches."""
        # Create more content
        for i in range(5):
            ContentMetadataFactory(
                content_key=f'course-{i + 3}',
                json_metadata={'title': f'Course {i + 3}'}
            )

        mock_translate.return_value = {'title': 'Translated'}

        # Run with small batch size
        call_command('populate_spanish_translations', batch_size=2)

        # All content should be translated
        self.assertEqual(ContentTranslation.objects.count(), 7)  # 2 original + 5 new

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.'
        'populate_spanish_translations.translate_object_fields'
    )
    def test_command_handles_translation_errors(self, mock_translate):
        """Test command continues after translation errors."""
        # First call succeeds, second fails, third succeeds
        mock_translate.side_effect = [
            {'title': 'Success 1'},
            Exception('Translation API error'),
            {'title': 'Success 2'},
        ]

        # Create third content
        ContentMetadataFactory(content_key='course-3', json_metadata={'title': 'Course 3'})

        # Run command - should not crash
        call_command('populate_spanish_translations')

        # Should have created 2 translations (skipped the one that errored)
        self.assertEqual(ContentTranslation.objects.count(), 2)

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.'
        'populate_spanish_translations.translate_object_fields'
    )
    def test_command_custom_language(self, mock_translate):
        """Test command supports custom language codes."""
        mock_translate.return_value = {'title': 'Titre français'}

        # Run command for French
        call_command('populate_spanish_translations', language='fr')

        # Should create French translation
        translation = ContentTranslation.objects.first()
        self.assertEqual(translation.language_code, 'fr')

    @mock.patch(
        'enterprise_catalog.apps.catalog.management.commands.'
        'populate_spanish_translations.translate_object_fields'
    )
    def test_command_translates_all_fields(self, mock_translate):
        """Test that command translates all relevant fields."""
        mock_translate.return_value = {
            'title': 'Título',
            'short_description': 'Descripción corta',
            'full_description': 'Descripción completa',
            'outcome': 'Resultados',
            'prerequisites': 'Requisitos',
            'subtitle': 'Subtítulo',
        }

        # Run command
        call_command('populate_spanish_translations')

        translation = ContentTranslation.objects.first()
        self.assertEqual(translation.title, 'Título')
        self.assertEqual(translation.short_description, 'Descripción corta')
        self.assertEqual(translation.full_description, 'Descripción completa')
        self.assertEqual(translation.outcome, 'Resultados')
        self.assertEqual(translation.prerequisites, 'Requisitos')
        self.assertEqual(translation.subtitle, 'Subtítulo')
