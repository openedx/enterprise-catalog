"""
Unit tests for Spanish translation in Algolia helper functions.
"""
import uuid

from django.test import TestCase

from enterprise_catalog.apps.api import tasks
from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.models import ContentTranslation
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)
from enterprise_catalog.apps.video_catalog.tests.factories import VideoFactory


class TestSpanishTranslationInAlgoliaHelpers(TestCase):
    """
    Tests for Spanish translation in add_metadata_to_algolia_objects and add_video_to_algolia_objects.
    """

    def test_add_metadata_to_algolia_objects_creates_spanish_objects(self):
        """
        Test that add_metadata_to_algolia_objects creates Spanish versions of all batched objects
        when translation exists.
        """
        # Setup
        course = ContentMetadataFactory(content_type=COURSE, content_key='test-course')
        # Create translation so Spanish objects are generated
        ContentTranslation.objects.create(
            content_metadata=course,
            language_code='es',
            title='Curso de Prueba'
        )

        algolia_products_by_object_id = {}
        catalog_uuid = str(uuid.uuid4())
        customer_uuid = str(uuid.uuid4())
        query_uuid = str(uuid.uuid4())

        # Execute
        tasks.add_metadata_to_algolia_objects(
            metadata=course,
            algolia_products_by_object_id=algolia_products_by_object_id,
            catalog_uuids=[catalog_uuid],
            customer_uuids=[customer_uuid],
            catalog_queries=[(query_uuid, "Test Query")],
            academy_uuids=[],
            academy_tags=[],
            video_ids=[],
        )

        # Verify both English and Spanish objects were created
        object_ids = list(algolia_products_by_object_id.keys())
        english_objects = [oid for oid in object_ids if '-es' not in oid]
        spanish_objects = [oid for oid in object_ids if '-es' in oid]

        # Should have 3 English objects (catalog, customer, query)
        assert len(english_objects) == 3
        # Should have 3 Spanish objects (catalog, customer, query)
        assert len(spanish_objects) == 3

        # Verify Spanish objects have correct format
        for spanish_oid in spanish_objects:
            assert '-es' in spanish_oid
            assert str(course.content_uuid) in spanish_oid
            assert algolia_products_by_object_id[spanish_oid]['language'] == 'es'

    def test_add_video_to_algolia_objects_skips_spanish_objects(self):
        """
        Test that add_video_to_algolia_objects skips Spanish versions (Video not supported yet).
        """
        # Setup
        video = VideoFactory()
        algolia_products_by_object_id = {}
        catalog_uuid = str(uuid.uuid4())
        customer_uuid = str(uuid.uuid4())
        query_uuid = str(uuid.uuid4())

        # Execute
        tasks.add_video_to_algolia_objects(
            video=video,
            algolia_products_by_object_id=algolia_products_by_object_id,
            customer_uuids=[customer_uuid],
            catalog_uuids=[catalog_uuid],
            catalog_queries=[(query_uuid, "Test Query")],
        )

        # Verify only English objects were created
        object_ids = list(algolia_products_by_object_id.keys())
        english_objects = [oid for oid in object_ids if '-es' not in oid]
        spanish_objects = [oid for oid in object_ids if '-es' in oid]

        # Should have 3 English objects (customer, catalog, query)
        assert len(english_objects) == 3
        # Should have 0 Spanish objects (Video not supported)
        assert len(spanish_objects) == 0

    def test_spanish_objects_include_same_uuids_as_english(self):
        """
        Test that Spanish objects contain the same UUID lists as their English counterparts.
        """
        # Setup
        course = ContentMetadataFactory(content_type=COURSE, content_key='test-course')
        # Create translation
        ContentTranslation.objects.create(
            content_metadata=course,
            language_code='es',
            title='Curso de Prueba'
        )

        algolia_products_by_object_id = {}
        catalog_uuids = [str(uuid.uuid4()), str(uuid.uuid4())]
        customer_uuids = [str(uuid.uuid4()), str(uuid.uuid4())]

        # Execute
        tasks.add_metadata_to_algolia_objects(
            metadata=course,
            algolia_products_by_object_id=algolia_products_by_object_id,
            catalog_uuids=catalog_uuids,
            customer_uuids=customer_uuids,
            catalog_queries=[],
            academy_uuids=[],
            academy_tags=[],
            video_ids=[],
        )

        # Find English and Spanish catalog objects
        english_catalog_obj = None
        spanish_catalog_obj = None

        for oid, obj in algolia_products_by_object_id.items():
            if 'catalog-uuids' in oid and '-es' not in oid:
                english_catalog_obj = obj
            elif 'catalog-uuids' in oid and '-es' in oid:
                spanish_catalog_obj = obj

        # Verify both objects exist and have same UUIDs
        assert english_catalog_obj is not None
        assert spanish_catalog_obj is not None
        english_uuids = english_catalog_obj.get('enterprise_catalog_uuids')
        spanish_uuids = spanish_catalog_obj.get('enterprise_catalog_uuids')
        assert english_uuids == spanish_uuids
