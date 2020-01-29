import uuid
from collections import OrderedDict

from django.test import override_settings
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from enterprise_catalog.apps.catalog.models import EnterpriseCatalog
from enterprise_catalog.apps.catalog.tests.factories import (
    USER_PASSWORD,
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
    UserFactory,
)


class EnterpriseCatalogViewSetTests(APITestCase):
    """
    Tests for the EnterpriseCatalogViewSet
    """
    def setUp(self):
        super(EnterpriseCatalogViewSetTests, self).setUp()
        self.enterprise_catalog = EnterpriseCatalogFactory()
        self.user = UserFactory(is_staff=True)
        self.client.login(username=self.user.username, password=USER_PASSWORD)
        self.new_catalog_uuid = uuid.uuid4()
        self.new_catalog_data = {
            'uuid': self.new_catalog_uuid,
            'title': 'Test Title',
            'enterprise_customer': uuid.uuid4(),
            'enabled_course_modes': '["verified"]',
            'publish_audit_enrollment_urls': True,
            'content_filter': '{"content_type":"course"}',
        }

    def _set_up_non_staff(self):
        """
        Helper for logging in as a non-staff user
        """
        self.client.logout()
        non_staff_user = UserFactory()
        self.client.login(username=non_staff_user.username, password=USER_PASSWORD)

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

    def test_list(self):
        """
        Verify the viewset returns a list of all enterprise catalogs
        """
        url = reverse('api:v1:enterprise-catalog-list')
        second_enterprise_catalog = EnterpriseCatalogFactory()
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        results = response.data['results']
        self.assertEqual(uuid.UUID(results[0]['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(uuid.UUID(results[1]['uuid']), second_enterprise_catalog.uuid)

    def test_list_unauthorized(self):
        """
        Verify the viewset rejects list for non-staff users
        """
        self._set_up_non_staff()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_detail(self):
        """
        Verify the viewset returns the details for a single enterprise catalog
        """
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(uuid.UUID(data['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual(data['title'], self.enterprise_catalog.title)
        self.assertEqual(uuid.UUID(data['enterprise_customer']), self.enterprise_catalog.enterprise_uuid)

    def test_detail_unauthorized(self):
        """
        Verify the viewset rejects non-staff users for the detail route
        """
        self._set_up_non_staff()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch(self):
        """
        Verify the viewset handles patching an enterprise catalog
        """
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

    def test_patch_unauthorized(self):
        """
        Verify the viewset rejects patch for non-staff users
        """
        self._set_up_non_staff()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_put(self):
        """
        Verify the viewset handles replacing an enterprise catalog
        """
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self._assert_correct_new_catalog_data(self.enterprise_catalog.uuid)  # The UUID should not have changed

    def test_put_unauthorized(self):
        """
        Verify the viewset rejects put for non-staff users
        """
        self._set_up_non_staff()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post(self):
        """
        Verify the viewset handles creating an enterprise catalog
        """
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self._assert_correct_new_catalog_data(self.new_catalog_uuid)

    def test_post_unauthorized(self):
        """
        Verify the viewset rejects post for non-staff users
        """
        self._set_up_non_staff()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def _get_contains_content_base_url(self, enterprise_catalog):
        """
        Helper to construct the base url for the contains_content_items endpoint
        """
        return reverse('api:v1:enterprise-catalog-contains-content-items', kwargs={'uuid': enterprise_catalog.uuid})

    def _assert_correct_response(self, url, expected_value):
        """
        Helper to assert that the contains_content_items endpoint specified by the url returns the correct value
        """
        response = self.client.get(url)
        self.assertEqual(response.json()['contains_content_items'], expected_value)

    def test_contains_content_items_no_params(self):
        """
        Verify the contains_content_items endpoint errors if no parameters are provided
        """
        response = self.client.get(self._get_contains_content_base_url(self.enterprise_catalog))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_contains_content_items_no_catalog_query(self):
        """
        Verify the contains_content_items endpoint returns False if there is no associated catalog query
        """
        no_catalog_query_catalog = EnterpriseCatalogFactory(catalog_query=None)
        url = self._get_contains_content_base_url(no_catalog_query_catalog) + '?program_uuids=test-uuid'
        self._assert_correct_response(url, False)

    def test_contains_content_items_keys_in_catalog(self):
        """
        Verify the contains_content_items endpoint returns True if the keys are explicitly in the catalog
        """
        content_key = 'test-key'
        associated_metadata = ContentMetadataFactory(content_key=content_key)
        # Link the catalog to the metadata it should be associated with
        self.enterprise_catalog.catalog_query.contentmetadata_set.add(associated_metadata)

        url = self._get_contains_content_base_url(self.enterprise_catalog) + '?course_run_ids=' + content_key
        self._assert_correct_response(url, True)

    def test_contains_content_items_parent_keys_in_catalog(self):
        """
        Verify the contains_content_items endpoint returns True if the parent's key is in the catalog
        """
        child_key = 'child-key'
        parent_metadata = ContentMetadataFactory(content_key='parent-key')
        ContentMetadataFactory(content_key=child_key, parent_content_key=parent_metadata.content_key)
        # Link the catalog to the parent metadata
        self.enterprise_catalog.catalog_query.contentmetadata_set.add(parent_metadata)

        url = self._get_contains_content_base_url(self.enterprise_catalog) + '?course_run_ids=' + child_key
        self._assert_correct_response(url, True)

    def test_contains_content_items_keys_not_in_catalog(self):
        """
        Verify the contains_content_items endpoint returns False if neither it or its parent's keys are in the catalog
        """
        associated_metadata = ContentMetadataFactory(content_key='some-unrelated-key')
        self.enterprise_catalog.catalog_query.contentmetadata_set.add(associated_metadata)

        url = self._get_contains_content_base_url(self.enterprise_catalog) + '?course_run_ids=' + 'test-key'
        self._assert_correct_response(url, False)

    def _get_content_metadata_url(self, enterprise_catalog):
        """
        Helper to get the get_content_metadata endpoint url for a given catalog
        """
        return reverse('api:v1:enterprise-catalog-get-content-metadata', kwargs={'uuid': enterprise_catalog.uuid})

    def test_get_content_metadata_no_catalog_query(self):
        """
        Verify the get_content_metadata endpoint returns no results if the catalog has no catalog query
        """
        no_catalog_query_catalog = EnterpriseCatalogFactory(catalog_query=None)
        url = self._get_content_metadata_url(no_catalog_query_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['results'], [])

    def test_get_content_metadata(self):
        """
        Verify the get_content_metadata endpoint returns all the metadata associated with a particular catalog
        """
        # Associate two pieces of metadata with the catalog, making sure the content keys are ordered for testing
        json_metadata_1 = {'content': 'fake'}
        metadata_1 = ContentMetadataFactory(json_metadata=json_metadata_1, content_key='first')
        self.enterprise_catalog.catalog_query.contentmetadata_set.add(metadata_1)
        json_metadata_2 = {'content': 'fake2'}
        metadata_2 = ContentMetadataFactory(json_metadata=json_metadata_2, content_key='second')
        self.enterprise_catalog.catalog_query.contentmetadata_set.add(metadata_2)

        url = self._get_content_metadata_url(self.enterprise_catalog)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(uuid.UUID(response.json()['uuid']), self.enterprise_catalog.uuid)
        self.assertEqual((response.json()['count']), 2)
        self.assertEqual(response.json()['title'], self.enterprise_catalog.title)
        self.assertEqual(uuid.UUID(response.json()['enterprise_customer']), self.enterprise_catalog.enterprise_uuid)
        self.assertEqual(response.json()['results'], [json_metadata_1, json_metadata_2])

    @override_settings(task_always_eager=True)
    def test_refresh_catalog_on_post_returns_200_ok(self):
        """
        Verify the refresh_metadata endpoint successfully updates the catalog metadata with a post request
        """
        url = reverse('api:v1:update-enterprise-catalog', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.post(url)
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
