""" Tests for catalog models. """

import json
from collections import OrderedDict
from unittest import mock

from django.test import TestCase, override_settings

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    PROGRAM,
)
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    ContentMetadataToQueries,
    update_contentmetadata_from_discovery,
)
from enterprise_catalog.apps.catalog.tests import factories


class TestModels(TestCase):
    """ Models tests. """

    def test_soft_deletion_model(self):
        metadata = factories.ContentMetadataFactory()
        query = factories.CatalogQueryFactory()
        assert len(ContentMetadataToQueries.objects.all()) == 0
        ContentMetadataToQueries.objects.get_or_create(catalog_query=query, content_metadata=metadata)
        assert len(ContentMetadataToQueries.objects.all()) == 1

        ContentMetadataToQueries.objects.get_queryset().clear()
        assert len(ContentMetadataToQueries.objects.all()) == 0
        assert len(ContentMetadataToQueries.all_objects.all()) == 1
        assert len(ContentMetadataToQueries.all_objects.get_queryset().dead()) == 1
        # Reset to test other customer query set functions
        ContentMetadataToQueries.all_objects.filter().update(deleted_at=None)

        assert len(ContentMetadataToQueries.objects.get_queryset().alive()) == 1

        ContentMetadataToQueries.objects.get_queryset().remove()
        assert len(ContentMetadataToQueries.objects.all()) == 0
        assert len(ContentMetadataToQueries.all_objects.all()) == 1

        ContentMetadataToQueries.all_objects.hard_delete()
        assert len(ContentMetadataToQueries.all_objects.all()) == 0

        ContentMetadataToQueries.objects.get_or_create(catalog_query=query, content_metadata=metadata)
        ContentMetadataToQueries.hard_delete(ContentMetadataToQueries.objects.first())
        assert len(ContentMetadataToQueries.objects.all()) == 0
        assert len(ContentMetadataToQueries.all_objects.all()) == 0

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    def test_soft_deletion_manager(self):
        # Setup
        content_metadata = factories.ContentMetadataFactory()
        first_query = factories.CatalogQueryFactory()
        second_query = factories.CatalogQueryFactory()
        content_metadata.catalog_query_mapping.set([first_query, second_query])

        # an extra content metadata and query items to make sure they aren't caught up in selects
        extra_content = factories.ContentMetadataFactory()
        extra_query = factories.CatalogQueryFactory()
        extra_content.catalog_query_mapping.set([extra_query])

        # Assert that we have two entries in the through table
        assert content_metadata.catalog_query_mapping.count() == 2
        assert content_metadata.catalog_queries.count() == 2

        # Remove one of the entries
        content_metadata.catalog_query_mapping.remove(first_query)

        # Check the through table and make sure we've soft deleted
        assert content_metadata.catalog_queries.count() == 1
        # We can access the deleted objects through all_objects
        assert content_metadata.catalog_query_mapping.through.all_objects.filter(
            content_metadata_id=content_metadata.id
        ).count() == 2

        # Re-add a removed query to test that we don't throw an integrity error. (there will be two entries in the
        # mapping for the first query, one deleted and one not)
        content_metadata.catalog_query_mapping.add(first_query)

        # Create another entry to play with
        third_query = factories.CatalogQueryFactory()
        # Set([], clear=True) should soft delete all other records besides the ones being set with a clear() method call
        content_metadata.catalog_query_mapping.set([third_query], clear=True)

        # This is an asymmetric relationship (content_metadata.catalog_query_mapping will associate with all FKs in the
        # through table) so the catalog_query_mapping will still hold the soft deleted records
        assert content_metadata.catalog_query_mapping.count() == 4

        # Check that all other entries have been soft deleted
        assert content_metadata.catalog_queries.count() == 1
        assert content_metadata.catalog_queries.first().id == third_query.id

        # Check that we can go in reverse and get the non-deleted content metadata belonging to a particular query
        assert not first_query.content_metadata.first() == content_metadata
        # Check that we still have access to the soft deleted records
        assert first_query.contentmetadata_set.count() == 2

        # Check that we are still able to hard delete if we really want
        assert content_metadata.catalog_queries.first()
        assert content_metadata.catalog_query_mapping.through.all_objects.filter(
            content_metadata_id=content_metadata.id
        ).count() == 4
        content_metadata.catalog_query_mapping.through.objects.filter(
            content_metadata_id=content_metadata.id
        ).hard_delete()
        assert not content_metadata.catalog_queries.first()
        assert content_metadata.catalog_query_mapping.through.all_objects.count() == 4

    def test_content_metadata_catalog_query_through_table(self):
        content_metadata = factories.ContentMetadataFactory()
        catalog_query = factories.CatalogQueryFactory()
        content_metadata.catalog_query_mapping.set([catalog_query])
        assert ContentMetadataToQueries.objects.all().count() == 1

        # soft delete
        ContentMetadataToQueries.objects.all().delete()
        assert ContentMetadataToQueries.all_objects.all().count() == 1
        assert ContentMetadataToQueries.all_objects.first().deleted_at

        # Make sure we don't throw integrity errors
        assert not ContentMetadataToQueries.objects.first()
        content_metadata.catalog_query_mapping.add(catalog_query)

        assert ContentMetadataToQueries.all_objects.all().count() == 2
        assert ContentMetadataToQueries.objects.all().count() == 1

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @mock.patch('enterprise_catalog.apps.api_client.discovery_cache.DiscoveryApiClient')
    def test_contentmetadata_update_from_discovery(self, mock_client):
        """
        update_contentmetadata_from_discovery should update or create ContentMetadata
        objects from the discovery service /search/all api call.
        """
        course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+testX'),
            ('key', 'edX+testX'),
            ('title', 'test course'),
        ])
        course_run_metadata = OrderedDict([
            ('aggregation_key', 'courserun:edX+testX'),
            ('key', 'course-v1:edX+testX+1'),
            ('title', 'test course run'),
        ])
        program_metadata = OrderedDict([
            ('aggregation_key', 'program:fake-uuid'),
            ('title', 'test program'),
            ('uuid', 'fake-uuid'),
        ])
        mock_client.return_value.get_metadata_by_query.return_value = [
            course_metadata,
            course_run_metadata,
            program_metadata,
        ]
        catalog = factories.EnterpriseCatalogFactory()

        self.assertEqual(ContentMetadata.objects.count(), 0)
        update_contentmetadata_from_discovery(catalog.catalog_query)
        mock_client.assert_called_once()
        self.assertEqual(ContentMetadata.objects.count(), 3)

        associated_metadata = catalog.content_metadata

        # Assert stored content metadata is correct for each type
        course_cm = ContentMetadata.objects.get(content_key=course_metadata['key'])
        self.assertEqual(course_cm.content_type, COURSE)
        self.assertEqual(course_cm.parent_content_key, None)
        self.assertEqual(course_cm.json_metadata, course_metadata)
        assert course_cm in associated_metadata

        course_run_cm = ContentMetadata.objects.get(content_key=course_run_metadata['key'])
        self.assertEqual(course_run_cm.content_type, COURSE_RUN)
        self.assertEqual(course_run_cm.parent_content_key, course_metadata['key'])
        self.assertEqual(course_run_cm.json_metadata, course_run_metadata)
        assert course_run_cm in associated_metadata

        program_cm = ContentMetadata.objects.get(content_key=program_metadata['uuid'])
        self.assertEqual(program_cm.content_type, PROGRAM)
        self.assertEqual(program_cm.parent_content_key, None)
        self.assertEqual(program_cm.json_metadata, program_metadata)
        assert program_cm in associated_metadata

        # Run again with existing ContentMetadata database objects, temporarily modifying
        # the json_metadata of the existing course to remove a field that will later be
        # added. Assert the existing json_metadata field is updated with the correct metadata
        # to include /search/all fields (e.g., aggregation_key).
        course_cm = ContentMetadata.objects.get(content_key=course_metadata['key'])
        course_cm.json_metadata = {
            'key': course_metadata['key'],
            'title': course_metadata['title'],
        }
        course_cm.save()
        update_contentmetadata_from_discovery(catalog.catalog_query)
        self.assertEqual(ContentMetadata.objects.count(), 3)  # assert all ContentMetadata objects are preserved
        course_cm = ContentMetadata.objects.get(content_key=course_metadata['key'])
        # assert json_metadata is updated to include fields plucked from /search/all metadata.
        self.assertEqual(
            json.dumps(course_cm.json_metadata, sort_keys=True),
            json.dumps(course_metadata, sort_keys=True),
        )

        # Run again and expect that we will unassociate some content metadata
        # from catalog query while perserving the content metadata objects
        # themselves.
        mock_client.return_value.get_metadata_by_query.return_value = [program_metadata]
        update_contentmetadata_from_discovery(catalog.catalog_query)
        self.assertEqual(ContentMetadata.objects.count(), 3)

        associated_metadata = catalog.content_metadata
        assert course_cm not in associated_metadata
        assert course_run_cm not in associated_metadata
        assert program_cm in associated_metadata

    @override_settings(DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT=0)
    @mock.patch('enterprise_catalog.apps.api_client.discovery_cache.DiscoveryApiClient')
    def test_contentmetadata_update_from_discovery_ignore_exec_ed(self, mock_client):
        """
        update_contentmetadata_from_discovery should update or create ContentMetadata
        objects from the discovery service /search/all api call.
        this test should filter out content which does not meet our course_type criteria
        """
        # this course SHOULD appear in the catalog we save
        audit_course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+testX'),
            ('key', 'edX+testX'),
            ('title', 'test course'),
            ('course_type', 'audit'),
        ])
        # this course SHOULD NOT appear in the catalog we save
        exec_ed_course_metadata = OrderedDict([
            ('aggregation_key', 'course:edX+testX'),
            ('key', 'edX+testX'),
            ('title', 'test course'),
            ('course_type', 'executive-education-2u'),
        ])
        course_run_metadata = OrderedDict([
            ('aggregation_key', 'courserun:edX+testX'),
            ('key', 'course-v1:edX+testX+1'),
            ('title', 'test course run'),
        ])
        program_metadata = OrderedDict([
            ('aggregation_key', 'program:fake-uuid'),
            ('title', 'test program'),
            ('uuid', 'fake-uuid'),
        ])
        mock_client.return_value.get_metadata_by_query.return_value = [
            audit_course_metadata,
            exec_ed_course_metadata,
            course_run_metadata,
            program_metadata,
        ]
        catalog = factories.EnterpriseCatalogFactory()

        self.assertEqual(ContentMetadata.objects.count(), 0)
        update_contentmetadata_from_discovery(catalog.catalog_query)
        mock_client.assert_called_once()
        self.assertEqual(ContentMetadata.objects.count(), 3)

        associated_metadata = catalog.content_metadata

        # Assert stored content metadata is correct for each type
        course_cm = ContentMetadata.objects.get(content_key=audit_course_metadata['key'])
        self.assertEqual(course_cm.content_type, COURSE)
        self.assertEqual(course_cm.parent_content_key, None)
        self.assertEqual(course_cm.json_metadata, audit_course_metadata)
        assert course_cm in associated_metadata

        course_run_cm = ContentMetadata.objects.get(content_key=course_run_metadata['key'])
        self.assertEqual(course_run_cm.content_type, COURSE_RUN)
        self.assertEqual(course_run_cm.parent_content_key, audit_course_metadata['key'])
        self.assertEqual(course_run_cm.json_metadata, course_run_metadata)
        assert course_run_cm in associated_metadata

        program_cm = ContentMetadata.objects.get(content_key=program_metadata['uuid'])
        self.assertEqual(program_cm.content_type, PROGRAM)
        self.assertEqual(program_cm.parent_content_key, None)
        self.assertEqual(program_cm.json_metadata, program_metadata)
        assert program_cm in associated_metadata

        # Run again with existing ContentMetadata database objects, temporarily modifying
        # the json_metadata of the existing course to remove a field that will later be
        # added. Assert the existing json_metadata field is updated with the correct metadata
        # to include /search/all fields (e.g., aggregation_key).
        course_cm = ContentMetadata.objects.get(content_key=audit_course_metadata['key'])
        course_cm.json_metadata = {
            'key': audit_course_metadata['key'],
            'title': audit_course_metadata['title'],
            'course_type': audit_course_metadata['course_type'],
        }
        course_cm.save()
        update_contentmetadata_from_discovery(catalog.catalog_query)
        self.assertEqual(ContentMetadata.objects.count(), 3)  # assert all ContentMetadata objects are preserved
        course_cm = ContentMetadata.objects.get(content_key=audit_course_metadata['key'])
        # assert json_metadata is updated to include fields plucked from /search/all metadata.
        self.assertEqual(
            json.dumps(course_cm.json_metadata, sort_keys=True),
            json.dumps(audit_course_metadata, sort_keys=True),
        )

        # Run again and expect that we will unassociate some content metadata
        # from catalog query while perserving the content metadata objects
        # themselves.
        mock_client.return_value.get_metadata_by_query.return_value = [program_metadata]
        update_contentmetadata_from_discovery(catalog.catalog_query)
        self.assertEqual(ContentMetadata.objects.count(), 3)

        associated_metadata = catalog.content_metadata
        assert course_cm not in associated_metadata
        assert course_run_cm not in associated_metadata
        assert program_cm in associated_metadata
