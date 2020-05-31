import uuid
from collections import OrderedDict
from operator import itemgetter

import ddt
import mock
from django.conf import settings
from django.db import IntegrityError
from django.utils.text import slugify
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings

from enterprise_catalog.apps.api.v1.tests.mixins import APITestMixin
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    PROGRAM,
)
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    ContentMetadata,
    EnterpriseCatalog,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
)


@ddt.ddt
class EnterpriseCatalogCRUDViewSetTests(APITestMixin):
    """
    Tests for the EnterpriseCatalogCRUDViewSet
    """

    def setUp(self):
        super(EnterpriseCatalogCRUDViewSetTests, self).setUp()
        self.set_up_staff()
        self.enterprise_catalog = EnterpriseCatalogFactory(
            enterprise_uuid=self.enterprise_uuid,
            enterprise_name=self.enterprise_name,
        )
        self.new_catalog_uuid = uuid.uuid4()
        self.new_catalog_data = {
            'uuid': self.new_catalog_uuid,
            'title': 'Test Title',
            'enterprise_customer': self.enterprise_uuid,
            'enterprise_customer_name': self.enterprise_name,
            'enabled_course_modes': '["verified"]',
            'publish_audit_enrollment_urls': True,
            'content_filter': '{"content_type":"course"}',
        }

    def _assert_correct_new_catalog_data(self, catalog_uuid):
        """
        Helper for verifying the data for a created/updated catalog
        """
        new_enterprise_catalog = EnterpriseCatalog.objects.get(uuid=catalog_uuid)
        self.assertEqual(new_enterprise_catalog.title, self.new_catalog_data['title'])
        self.assertEqual(new_enterprise_catalog.enabled_course_modes, ['verified'])
        self.assertEqual(
            new_enterprise_catalog.publish_audit_enrollment_urls,
            self.new_catalog_data['publish_audit_enrollment_urls'],
        )
        self.assertEqual(
            new_enterprise_catalog.catalog_query.content_filter,
            OrderedDict([('content_type', 'course')]),
        )

    def test_detail_unauthorized_catalog_learner(self):
        """
        Verify the viewset rejects catalog learners for the detail route
        """
        self.set_up_catalog_learner()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_unauthorized_catalog_learner(self):
        """
        Verify the viewset rejects patch for catalog learners
        """
        self.set_up_catalog_learner()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_put_unauthorized_catalog_learner(self):
        """
        Verify the viewset rejects put for catalog learners
        """
        self.set_up_catalog_learner()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_unauthorized_catalog_learner(self):
        """
        Verify the viewset rejects post for catalog learners
        """
        self.set_up_catalog_learner()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @ddt.data(
        (False),
        (True),
    )
    def test_detail(self, is_implicit_check):
        """
        Verify the viewset returns the details for a single enterprise catalog
        """
        if is_implicit_check:
            self.remove_role_assignments()

        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(uuid.UUID(data['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(data['title'], self.enterprise_catalog.title)
        self.assertEqual(uuid.UUID(data['enterprise_customer']), self.enterprise_catalog.enterprise_uuid)

    def test_detail_unauthorized_non_catalog_admin(self):
        """
        Verify the viewset rejects users that are not catalog admins for the detail route
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_detail_unauthorized_incorrect_jwt_context(self):
        """
        Verify the viewset rejects users that are catalog admins with an invalid
        context (i.e., enterprise uuid) for the detail route.
        """
        enterprise_catalog = EnterpriseCatalogFactory()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @mock.patch('enterprise_catalog.apps.api.v1.serializers.update_catalog_metadata_task.delay')
    @ddt.data(
        (False),
        (True),
    )
    def test_patch(self, is_implicit_check, mock_async_task):
        """
        Verify the viewset handles patching an enterprise catalog
        """
        if is_implicit_check:
            self.remove_role_assignments()

        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verify that only the data we specifically patched changed
        self.assertEqual(response.data['title'], patch_data['title'])
        patched_catalog = EnterpriseCatalog.objects.get(uuid=self.enterprise_catalog.uuid)
        self.assertEqual(patched_catalog.catalog_query, self.enterprise_catalog.catalog_query)
        self.assertEqual(patched_catalog.enterprise_uuid, self.enterprise_catalog.enterprise_uuid)
        self.assertEqual(patched_catalog.enabled_course_modes, self.enterprise_catalog.enabled_course_modes)
        self.assertEqual(
            patched_catalog.publish_audit_enrollment_urls,
            self.enterprise_catalog.publish_audit_enrollment_urls,
        )
        mock_async_task.assert_called_once()

    def test_patch_unauthorized_non_catalog_admin(self):
        """
        Verify the viewset rejects patch for users that are not catalog admins
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_unauthorized_incorrect_jwt_context(self):
        """
        Verify the viewset rejects patch for users that are catalog admins with an invalid
        context (i.e., enterprise uuid)
        """
        enterprise_catalog = EnterpriseCatalogFactory()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': enterprise_catalog.uuid})
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @mock.patch('enterprise_catalog.apps.api.v1.serializers.update_catalog_metadata_task.delay')
    @ddt.data(
        (False),
        (True),
    )
    def test_put(self, is_implicit_check, mock_async_task):
        """
        Verify the viewset handles replacing an enterprise catalog
        """
        if is_implicit_check:
            self.remove_role_assignments()

        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self._assert_correct_new_catalog_data(self.enterprise_catalog.uuid)  # The UUID should not have changed
        mock_async_task.assert_called_once()

    def test_put_unauthorized_non_catalog_admin(self):
        """
        Verify the viewset rejects put for users that are not catalog admins
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_put_unauthorized_incorrect_jwt_context(self):
        """
        Verify the viewset rejects put for users that are catalog admins with an invalid
        context (i.e., enterprise uuid)
        """
        enterprise_catalog = EnterpriseCatalogFactory()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @mock.patch('enterprise_catalog.apps.api.v1.serializers.update_catalog_metadata_task.delay')
    @ddt.data(
        (False),
        (True),
    )
    def test_post(self, is_implicit_check, mock_async_task):
        """
        Verify the viewset handles creating an enterprise catalog
        """
        if is_implicit_check:
            self.remove_role_assignments()

        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self._assert_correct_new_catalog_data(self.new_catalog_uuid)
        mock_async_task.assert_called_once()

    @mock.patch('enterprise_catalog.apps.api.v1.serializers.update_catalog_metadata_task.delay')
    def test_post_integrity_error(self, mock_async_task):
        """
        Verify the viewset raises error when creating a duplicate enterprise catalog
        """
        url = reverse('api:v1:enterprise-catalog-list')
        self.client.post(url, self.new_catalog_data)
        with self.assertRaises(IntegrityError):
            self.client.post(url, self.new_catalog_data)
        # Note: we're hitting the endpoint twice here, but this task should
        # only be run once, as we should error from an integrity error the
        # second time through
        mock_async_task.assert_called_once()

    def test_post_unauthorized_non_catalog_admin(self):
        """
        Verify the viewset rejects post for users that are not catalog admins
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_unauthorized_incorrect_jwt_context(self):
        """
        Verify the viewset rejects post for users that are catalog admins with an invalid
        context (i.e., enterprise uuid)
        """
        catalog_data = {
            'uuid': self.new_catalog_uuid,
            'title': 'Test Title',
            'enterprise_customer': uuid.uuid4(),
            'enabled_course_modes': '["verified"]',
            'publish_audit_enrollment_urls': True,
            'content_filter': '{"content_type":"course"}',
        }
        self.remove_role_assignments()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@ddt.ddt
class EnterpriseCatalogCRUDViewSetListTests(APITestMixin):
    """
    Tests for the EnterpriseCatalogCRUDViewSet list endpoint.
    """

    def setUp(self):
        super().setUp()
        self.set_up_staff_user()
        self.enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)

    def test_list_for_superusers(self):
        """
        Verify the viewset returns a list of all enterprise catalogs for superusers
        """
        self.set_up_superuser()
        url = reverse('api:v1:enterprise-catalog-list')
        second_enterprise_catalog = EnterpriseCatalogFactory()
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        results = response.data['results']
        self.assertEqual(uuid.UUID(results[0]['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(uuid.UUID(results[1]['uuid']), second_enterprise_catalog.uuid)

    def test_empty_list_for_non_catalog_admin(self):
        """
        Verify the viewset returns an empty list for users that are staff but not catalog admins.
        """
        self.set_up_invalid_jwt_role()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    @ddt.data(
        False,
        True,
    )
    def test_one_catalog_for_catalog_admins(self, is_role_assigned_via_jwt):
        """
        Verify the viewset returns a single catalog (when multiple exist) for catalog admins of a certain enterprise.
        """
        if is_role_assigned_via_jwt:
            self.assign_catalog_admin_jwt_role()
        else:
            self.assign_catalog_admin_feature_role()

        # create an additional catalog from a different enterprise,
        # and make sure we don't see it in the response results.
        EnterpriseCatalogFactory(enterprise_uuid=uuid.uuid4())

        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        results = response.data['results']
        self.assertEqual(uuid.UUID(results[0]['uuid']), self.enterprise_catalog.uuid)

    @ddt.data(
        False,
        True,
    )
    def test_multiple_catalogs_for_catalog_admins(self, is_role_assigned_via_jwt):
        """
        Verify the viewset returns multiple catalogs for catalog admins of two different enterprises.
        """
        second_enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=uuid.uuid4())

        if is_role_assigned_via_jwt:
            self.assign_catalog_admin_jwt_role(
                self.enterprise_uuid,
                second_enterprise_catalog.enterprise_uuid,
            )
        else:
            self.assign_catalog_admin_feature_role(enterprise_uuids=[
                self.enterprise_uuid,
                second_enterprise_catalog.enterprise_uuid,
            ])

        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        results = response.data['results']
        self.assertEqual(uuid.UUID(results[0]['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(uuid.UUID(results[1]['uuid']), second_enterprise_catalog.uuid)

    @ddt.data(
        False,
        True,
    )
    def test_every_catalog_for_catalog_admins(self, is_role_assigned_via_jwt):
        """
        Verify the viewset returns catalogs of all enterprises for admins with wildcard permission.
        """
        if is_role_assigned_via_jwt:
            self.assign_catalog_admin_jwt_role('*')
        else:
            # This will cause a feature role assignment to be created with a null enterprise UUID,
            # which is interpretted as having access to catalogs of ANY enterprise.
            self.assign_catalog_admin_feature_role(enterprise_uuids=[None])

        catalog_b = EnterpriseCatalogFactory(enterprise_uuid=uuid.uuid4())
        catalog_c = EnterpriseCatalogFactory(enterprise_uuid=uuid.uuid4())

        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        results = response.data['results']
        self.assertEqual(uuid.UUID(results[0]['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(uuid.UUID(results[1]['uuid']), catalog_b.uuid)
        self.assertEqual(uuid.UUID(results[2]['uuid']), catalog_c.uuid)

    def test_list_unauthorized_catalog_learner(self):
        """
        Verify the viewset rejects list for catalog learners
        """
        self.set_up_catalog_learner()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class EnterpriseCatalogContainsContentItemsTests(APITestMixin):
    """
    Tests on the contains_content_items on enterprise catalogs endpoint
    """

    def setUp(self):
        super(EnterpriseCatalogContainsContentItemsTests, self).setUp()
        # Set up catalog.has_learner_access permissions
        self.set_up_catalog_learner()
        self.enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)

    def _get_contains_content_base_url(self, enterprise_catalog):
        """
        Helper to construct the base url for the contains_content_items endpoint
        """
        return reverse('api:v1:enterprise-catalog-contains-content-items', kwargs={'uuid': enterprise_catalog.uuid})

    def test_contains_content_items_no_params(self):
        """
        Verify the contains_content_items endpoint errors if no parameters are provided
        """
        response = self.client.get(self._get_contains_content_base_url(self.enterprise_catalog))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_contains_content_items_unauthorized_incorrect_jwt_context(self):
        """
        Verify the contains_content_items endpoint rejects users with an invalid JWT context (i.e., enterprise uuid)
        """
        enterprise_catalog = EnterpriseCatalogFactory()
        self.remove_role_assignments()
        url = self._get_contains_content_base_url(enterprise_catalog) + '?course_run_ids=fakeX'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_contains_content_items_implicit_access(self):
        """
        Verify the contains_content_items endpoint responds with 200 OK for user with implicit JWT access
        """
        self.remove_role_assignments()
        url = self._get_contains_content_base_url(self.enterprise_catalog) + '?course_run_ids=fakeX'
        self.assert_correct_contains_response(url, False)

    def test_contains_content_items_no_catalog_query(self):
        """
        Verify the contains_content_items endpoint returns False if there is no associated catalog query
        """
        no_catalog_query_catalog = EnterpriseCatalogFactory(
            catalog_query=None,
            enterprise_uuid=self.enterprise_uuid,
        )
        url = self._get_contains_content_base_url(no_catalog_query_catalog) + '?program_uuids=test-uuid'
        self.assert_correct_contains_response(url, False)

    def test_contains_content_items_keys_in_catalog(self):
        """
        Verify the contains_content_items endpoint returns True if the keys are explicitly in the catalog
        """
        content_key = 'test-key'
        associated_metadata = ContentMetadataFactory(content_key=content_key)
        self.add_metadata_to_catalog(self.enterprise_catalog, [associated_metadata])

        url = self._get_contains_content_base_url(self.enterprise_catalog) + '?course_run_ids=' + content_key
        self.assert_correct_contains_response(url, True)

    def test_contains_content_items_parent_keys_in_catalog(self):
        """
        Verify the contains_content_items endpoint returns True if the parent's key is in the catalog
        """
        parent_metadata = ContentMetadataFactory(content_key='parent-key')
        associated_metadata = ContentMetadataFactory(
            content_key='child-key+101x',
            parent_content_key=parent_metadata.content_key
        )
        self.add_metadata_to_catalog(self.enterprise_catalog, [associated_metadata])

        query_string = '?course_run_ids=' + parent_metadata.content_key
        url = self._get_contains_content_base_url(self.enterprise_catalog) + query_string
        self.assert_correct_contains_response(url, True)

    def test_contains_content_items_course_run_keys_in_catalog(self):
        """
        Verify the contains_content_items endpoint returns True if a course run's key is in the catalog
        """
        content_key = 'course-content-key'
        course_run_content_key = 'course-run-content-key'
        associated_metadata = ContentMetadataFactory(
            content_key=content_key,
            json_metadata={
                'key': content_key,
                'marketing_url': 'http://marketing.url/{}'.format(content_key),
                'course_runs': [{'key': course_run_content_key}],
            }
        )
        self.add_metadata_to_catalog(self.enterprise_catalog, [associated_metadata])

        url = self._get_contains_content_base_url(self.enterprise_catalog) + '?course_run_ids=' + course_run_content_key
        self.assert_correct_contains_response(url, True)

    def test_contains_content_items_keys_not_in_catalog(self):
        """
        Verify the contains_content_items endpoint returns False if neither it or its parent's keys are in the catalog
        """
        associated_metadata = ContentMetadataFactory(content_key='some-unrelated-key')
        self.add_metadata_to_catalog(self.enterprise_catalog, [associated_metadata])

        url = self._get_contains_content_base_url(self.enterprise_catalog) + '?course_run_ids=' + 'test-key'
        self.assert_correct_contains_response(url, False)


class EnterpriseCatalogGetContentMetadataTests(APITestMixin):
    """
    Tests on the get_content_metadata endpoint
    """

    def setUp(self):
        super().setUp()
        # Set up catalog.has_learner_access permissions
        self.set_up_catalog_learner()
        self.enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        # Delete any existing ContentMetadata records.
        ContentMetadata.objects.all().delete()

    def _get_content_metadata_url(self, enterprise_catalog):
        """
        Helper to get the get_content_metadata endpoint url for a given catalog
        """
        return reverse('api:v1:enterprise-catalog-get-content-metadata', kwargs={'uuid': enterprise_catalog.uuid})

    def _get_expected_json_metadata(self, content_metadata):
        """
        Helper to get the expected json_metadata from the passed in content_metadata instance
        """
        content_type = content_metadata.content_type
        updated_json_metadata = content_metadata.json_metadata.copy()

        enrollment_url = '{}/enterprise/{}/{}/{}/enroll/?catalog={}&utm_medium=enterprise&utm_source={}'
        marketing_url = '{}?utm_medium=enterprise&utm_source={}'

        if updated_json_metadata.get('marketing_url'):
            updated_json_metadata['marketing_url'] = marketing_url.format(
                updated_json_metadata['marketing_url'],
                slugify(self.enterprise_catalog.enterprise_name),
            )

        if content_type in (COURSE, COURSE_RUN):
            updated_json_metadata['enrollment_url'] = enrollment_url.format(
                settings.LMS_BASE_URL,
                self.enterprise_catalog.enterprise_uuid,
                'course',
                updated_json_metadata['key'],
                self.enterprise_catalog.uuid,
                self.enterprise_catalog.enterprise_name,
            )
            if content_type == COURSE:
                updated_json_metadata['active'] = False
        elif content_type == PROGRAM:
            updated_json_metadata['enrollment_url'] = enrollment_url.format(
                settings.LMS_BASE_URL,
                self.enterprise_catalog.enterprise_uuid,
                'program',
                updated_json_metadata['key'],
                self.enterprise_catalog.uuid,
                self.enterprise_catalog.enterprise_name,
            )

        return updated_json_metadata

    def test_get_content_metadata_unauthorized_invalid_permissions(self):
        """
        Verify the get_content_metadata endpoint rejects users with invalid permissions
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = self._get_content_metadata_url(self.enterprise_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_content_metadata_unauthorized_incorrect_jwt_context(self):
        """
        Verify the get_content_metadata endpoint rejects catalog learners
        with an incorrect JWT context (i.e., enterprise uuid)
        """
        enterprise_catalog = EnterpriseCatalogFactory()
        self.remove_role_assignments()
        url = self._get_content_metadata_url(enterprise_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_content_metadata_implicit_access(self):
        """
        Verify the get_content_metadata endpoint responds with 200 OK for
        user with implicit JWT access
        """
        self.remove_role_assignments()
        url = self._get_content_metadata_url(self.enterprise_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_content_metadata_no_catalog_query(self):
        """
        Verify the get_content_metadata endpoint returns no results if the catalog has no catalog query
        """
        no_catalog_query_catalog = EnterpriseCatalogFactory(
            catalog_query=None,
            enterprise_uuid=self.enterprise_uuid,
        )
        url = self._get_content_metadata_url(no_catalog_query_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['results'], [])

    def test_get_content_metadata(self):
        """
        Verify the get_content_metadata endpoint returns all the metadata associated with a particular catalog
        """
        # Create enough metadata to force pagination
        metadata = ContentMetadataFactory.create_batch(api_settings.PAGE_SIZE + 1)
        self.add_metadata_to_catalog(self.enterprise_catalog, metadata)
        url = self._get_content_metadata_url(self.enterprise_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual((response_data['count']), api_settings.PAGE_SIZE + 1)
        self.assertEqual(uuid.UUID(response_data['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(response_data['title'], self.enterprise_catalog.title)
        self.assertEqual(uuid.UUID(response_data['enterprise_customer']), self.enterprise_catalog.enterprise_uuid)

        # Check that the first page contains all but the last metadata
        expected_metadata = sorted([
            self._get_expected_json_metadata(item)
            for item in metadata
        ], key=itemgetter('key'))
        actual_metadata = response_data['results']
        self.assertEqual(actual_metadata, expected_metadata[:-1])

        # Check that the second page contains the last metadata
        second_page_response = self.client.get(response_data['next'])
        self.assertEqual(second_page_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_page_response.json()['results'], [expected_metadata[-1]])

    def test_get_content_metadata_traverse_pagination(self):
        """
        Verify the get_content_metadata endpoint returns all metadata on one page if the traverse pagination query
        parameter is added.
        """
        # Create enough metadata to force pagination (if the query parameter wasn't sent)
        metadata = ContentMetadataFactory.create_batch(api_settings.PAGE_SIZE + 1)
        self.add_metadata_to_catalog(self.enterprise_catalog, metadata)
        url = self._get_content_metadata_url(self.enterprise_catalog) + '?traverse_pagination=1'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual((response_data['count']), api_settings.PAGE_SIZE + 1)
        self.assertEqual(uuid.UUID(response_data['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(response_data['title'], self.enterprise_catalog.title)
        self.assertEqual(uuid.UUID(response_data['enterprise_customer']), self.enterprise_catalog.enterprise_uuid)

        # Check that the page contains all the metadata
        expected_metadata = sorted([
            self._get_expected_json_metadata(item)
            for item in metadata
        ], key=itemgetter('key'))
        actual_metadata = response_data['results']
        self.assertEqual(actual_metadata, expected_metadata)


class EnterpriseCatalogRefreshDataFromDiscoveryTests(APITestMixin):
    """
    Tests for the update catalog metadata view
    """

    def setUp(self):
        super(EnterpriseCatalogRefreshDataFromDiscoveryTests, self).setUp()
        self.set_up_staff()
        self.enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)

    @mock.patch('enterprise_catalog.apps.api.v1.views.update_catalog_metadata_task.delay')
    def test_refresh_catalog_on_post_returns_200_ok(self, mock_task):
        """
        Verify the refresh_metadata endpoint returns a status of 200 OK when hit with a valid UUID
        """
        mock_task.return_value = mock.Mock()
        mock_task.return_value.task_id = 'deadbeef-0123456789-deadbeef'
        url = reverse('api:v1:update-enterprise-catalog', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.post(url)
        mock_task.assert_called()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_refresh_catalog_on_get_returns_405_not_allowed(self):
        """
        Verify the refresh_metadata endpoint does not update the catalog metadata with a get request
        """
        url = reverse('api:v1:update-enterprise-catalog', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_refresh_catalog_on_invalid_uuid_returns_400_bad_request(self):
        """
        Verify the refresh_metadata endpoint returns an HTTP_400_BAD_REQUEST status when passed an invalid ID
        """
        catalog_uuid = self.enterprise_catalog.uuid
        EnterpriseCatalog.objects.all().delete()
        url = reverse('api:v1:update-enterprise-catalog', kwargs={'uuid': catalog_uuid})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class EnterpriseCustomerViewSetTests(APITestMixin):
    """
    Tests for the EnterpriseCustomerViewSet
    """

    def setUp(self):
        super(EnterpriseCustomerViewSetTests, self).setUp()
        # clean up any stale test objects
        CatalogQuery.objects.all().delete()
        ContentMetadata.objects.all().delete()
        EnterpriseCatalog.objects.all().delete()

        self.enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)

        # Set up catalog.has_learner_access permissions
        self.set_up_catalog_learner()

    def _get_contains_content_base_url(self, enterprise_uuid=None):
        """
        Helper to construct the base url for the contains_content_items endpoint
        """
        return reverse(
            'api:v1:enterprise-customer-contains-content-items',
            kwargs={'enterprise_uuid': enterprise_uuid or self.enterprise_uuid},
        )

    def test_contains_content_items_unauthorized_non_catalog_learner(self):
        """
        Verify the contains_content_items endpoint rejects users that are not catalog learners
        """
        self.set_up_invalid_jwt_role()
        self.remove_role_assignments()
        url = self._get_contains_content_base_url() + '?course_run_ids=fakeX'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_contains_content_items_unauthorized_incorrect_jwt_context(self):
        """
        Verify the contains_content_items endpoint rejects users that are catalog learners
        with an incorrect JWT context (i.e., enterprise uuid)
        """
        self.remove_role_assignments()
        base_url = self._get_contains_content_base_url(enterprise_uuid=uuid.uuid4())
        url = base_url + '?course_run_ids=fakeX'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_contains_content_items_implicit_access(self):
        """
        Verify the contains_content_items endpoint responds with 200 OK for
        user with implicit JWT access
        """
        self.remove_role_assignments()
        url = self._get_contains_content_base_url() + '?program_uuids=fakeX'
        self.assert_correct_contains_response(url, False)

    def test_contains_content_items_no_params(self):
        """
        Verify the contains_content_items endpoint errors if no parameters are provided
        """
        response = self.client.get(self._get_contains_content_base_url())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_contains_content_items_not_in_catalogs(self):
        """
        Verify the contains_content_items endpoint returns False if the content is not in any associated catalog
        """
        self.add_metadata_to_catalog(self.enterprise_catalog, [ContentMetadataFactory()])

        url = self._get_contains_content_base_url() + '?program_uuids=this-is-not-the-uuid-youre-looking-for'
        self.assert_correct_contains_response(url, False)

    def test_contains_content_items_in_catalogs(self):
        """
        Verify the contains_content_items endpoint returns True if the content is in any associated catalog
        """
        content_metadata = ContentMetadataFactory()
        self.add_metadata_to_catalog(self.enterprise_catalog, [content_metadata])

        # Create a second catalog that has the content we're looking for
        content_key = 'fake-key+101x'
        second_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        relevant_content = ContentMetadataFactory(content_key=content_key)
        self.add_metadata_to_catalog(second_catalog, [relevant_content])

        url = self._get_contains_content_base_url() + '?course_run_ids=' + content_key
        self.assert_correct_contains_response(url, True)
