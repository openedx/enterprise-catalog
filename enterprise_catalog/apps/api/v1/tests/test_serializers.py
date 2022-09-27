from uuid import uuid4

from django.db import transaction
from django.test import TestCase
from rest_framework import serializers

from enterprise_catalog.apps.api.v1.serializers import (
    find_and_modify_catalog_query,
)
from enterprise_catalog.apps.catalog.models import CatalogQuery
from enterprise_catalog.apps.catalog.utils import get_content_filter_hash


class FindCatalogQueryTest(TestCase):
    """
    Tests for API utils
    """

    def setUp(self):
        super().setUp()
        self.old_uuid = uuid4()
        self.old_filter = {'key': ['arglblargl']}
        self.old_catalog_query = CatalogQuery.objects.create(
            content_filter=self.old_filter,
            content_filter_hash=get_content_filter_hash(self.old_filter),
            uuid=self.old_uuid
        )

    def tearDown(self):
        super().tearDown()
        # clean up any stale test objects
        CatalogQuery.objects.all().delete()

    def test_new_uuid_old_filter_saves_query_with_new_uuid(self):
        old_filter = {'key': ['course:testing']}
        CatalogQuery.objects.create(
            content_filter=old_filter,
            content_filter_hash=get_content_filter_hash(old_filter)
        )
        new_uuid = uuid4()
        result = find_and_modify_catalog_query(old_filter, new_uuid)
        self.assertEqual((result.content_filter, result.uuid), (old_filter, new_uuid))

    def test_new_uuid_new_filter_creates_new_query(self):
        new_uuid = uuid4()
        new_filter = {'key': ['course:testingnnnnnn']}
        result = find_and_modify_catalog_query(new_filter, new_uuid)
        self.assertEqual((result.content_filter, result.uuid), (new_filter, new_uuid))

    def test_old_uuid_new_filter_saves_query_with_new_filter(self):
        old_uuid = uuid4()
        old_filter = {'key': ['plpplplpl']}
        new_filter = {'key': ['roger']}
        CatalogQuery.objects.create(
            content_filter=old_filter,
            content_filter_hash=get_content_filter_hash(old_filter),
            uuid=old_uuid
        )
        result = find_and_modify_catalog_query(new_filter, old_uuid)
        self.assertEqual((result.content_filter, result.uuid), (new_filter, old_uuid))

    def test_old_uuid_old_filter_changes_nothing(self):
        result = find_and_modify_catalog_query(self.old_filter, self.old_uuid)
        self.assertEqual(result, self.old_catalog_query)

    def test_no_uuid_old_filter_changes_nothing(self):
        result = find_and_modify_catalog_query(self.old_filter)
        self.assertEqual(result, self.old_catalog_query)

    def test_no_uuid_old_filter_diff_exec_ed_changes_nothing(self):
        """
        When no catalog_query_uuid is provided, the content filter matches an existing query,
        but a different value than the existing query is provided for ``include_exec_ed_2u_courses``,
        a new CatalogQuery instance should be created (because that does not violate the unique
        constraint on ``(content_filter_hash, include_exec_ed_2u_courses)``.
        """
        result = find_and_modify_catalog_query(self.old_filter, include_exec_ed_2u_courses=True)
        self.assertNotEqual(result, self.old_catalog_query)
        self.assertEqual(result.content_filter_hash, self.old_catalog_query.content_filter_hash)
        self.assertTrue(result.include_exec_ed_2u_courses)

    def test_no_uuid_new_filter_creates_new_query(self):
        new_filter = {'key': ['mmmmmmmm']}
        result = find_and_modify_catalog_query(new_filter)
        self.assertEqual(result.content_filter, new_filter)

    def test_validation_error_raised_on_duplication(self):
        dupe_filter = {'key': ['summerxbreeze']}
        uuid_to_update = uuid4()
        CatalogQuery.objects.create(
            content_filter=dupe_filter,
            uuid=uuid4()
        )
        CatalogQuery.objects.create(
            content_filter={'key': ['tempfilter']},
            uuid=uuid_to_update
        )
        with transaction.atomic():
            self.assertRaises(
                serializers.ValidationError,
                find_and_modify_catalog_query,
                dupe_filter,
                uuid_to_update
            )

    def test_no_error_for_dupe_uuid_but_diff_exec_ed_inclusion(self):
        """
        Should be able to modify an existing query to have the same
        content filter (hash) as another existing query, as long as
        the former has a different ``include_exec_ed_2u_courses`` value
        than the latter.
        """
        dupe_filter = {'key': ['summerxbreeze']}
        uuid_to_update = uuid4()
        query_no_exec_ed_courses = CatalogQuery.objects.create(
            content_filter=dupe_filter,
            uuid=uuid4(),
        )
        CatalogQuery.objects.create(
            content_filter={'key': ['tempfilter']},
            uuid=uuid_to_update,
        )
        modified_query = find_and_modify_catalog_query(dupe_filter, include_exec_ed_2u_courses=True)
        self.assertEqual(
            modified_query.content_filter_hash,
            query_no_exec_ed_courses.content_filter_hash,
        )

    def test_old_uuid_new_title_saves_existing_query_with_title(self):
        new_title = 'testing'
        result = find_and_modify_catalog_query(self.old_filter, self.old_uuid, new_title)
        self.assertEqual(
            (result.content_filter, result.uuid, result.title),
            (self.old_filter, self.old_uuid, new_title)
        )

    def test_title_duplication_causes_error(self):
        query_filter = {'key': ['summerxbreeze']}
        second_filter = {'key': ['winterxfreeze']}
        title = 'testdupe'
        uuid_to_update = uuid4()
        CatalogQuery.objects.create(
            content_filter=query_filter,
            uuid=uuid4(),
            title=title
        )
        CatalogQuery.objects.create(
            content_filter=second_filter,
            uuid=uuid_to_update,
            title='temp_title'
        )
        with transaction.atomic():
            self.assertRaises(
                serializers.ValidationError,
                find_and_modify_catalog_query,
                second_filter,
                uuid_to_update,
                title
            )
