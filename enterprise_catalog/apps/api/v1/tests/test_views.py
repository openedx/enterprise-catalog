from collections import OrderedDict
from uuid import uuid4

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from enterprise_catalog.apps.api.v1.tests.mixins import SerializationMixin
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog
from enterprise_catalog.apps.catalog.tests.factories import (
    USER_PASSWORD,
    EnterpriseCatalogFactory,
    UserFactory,
)


class EnterpriseCatalogViewSetTests(SerializationMixin, APITestCase):
    """
    Tests for the EnterpriseCatalogViewSet
    """
    def setUp(self):
        super(EnterpriseCatalogViewSetTests, self).setUp()
        self.enterprise_catalog = EnterpriseCatalogFactory()
        self.user = UserFactory(is_staff=True)
        self.client.login(username=self.user.username, password=USER_PASSWORD)
        self.new_catalog_uuid = uuid4()
        self.new_catalog_data = {
            'uuid': self.new_catalog_uuid,
            'title': 'Test Title',
            'enterprise_customer': uuid4(),
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

    def _assert_correct_new_catalog_data(self, uuid):
        """
        Helper for verifying the data for a created/updated catalog
        """
        new_enterprise_catalog = EnterpriseCatalog.objects.get(uuid=uuid)
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
        Verify the endpoint returns a list of all enterprise catalogs
        """
        url = reverse('api:v1:enterprise-catalog-list')
        second_enterprise_catalog = EnterpriseCatalogFactory(catalog_query__content_filter='{"content_type":"course"}')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['results'],
            self.serialize_enterprise_catalog([self.enterprise_catalog, second_enterprise_catalog], many=True)
        )

    def test_list_unauthorized(self):
        """
        Verify the endpoint rejects list for non-staff users
        """
        self._set_up_non_staff()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_detail(self):
        """
        Verify the endpoint returns the details for a single enterprise catalog
        """
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.serialize_enterprise_catalog(self.enterprise_catalog))

    def test_detail_unauthorized(self):
        """
        Verify the endpoint rejects non-staff users for the detail route
        """
        self._set_up_non_staff()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch(self):
        """
        Verify the endpoint handles patching an enterprise catalog
        """
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], patch_data['title'])

    def test_patch_unauthorized(self):
        """
        Verify the endpoint rejects patch for non-staff users
        """
        self._set_up_non_staff()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        patch_data = {'title': 'Patch title'}
        response = self.client.patch(url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_put(self):
        """
        Verify the endpoint handles replacing an enterprise catalog
        """
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self._assert_correct_new_catalog_data(self.enterprise_catalog.uuid)  # The UUID should not have changed

    def test_put_unauthorized(self):
        """
        Verify the endpoint rejects put for non-staff users
        """
        self._set_up_non_staff()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.put(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post(self):
        """
        Verify the endpoint handles creating an enterprise catalog
        """
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self._assert_correct_new_catalog_data(self.new_catalog_uuid)

    def test_post_unauthorized(self):
        """
        Verify the endpoint rejects post for non-staff users
        """
        self._set_up_non_staff()
        url = reverse('api:v1:enterprise-catalog-list')
        response = self.client.post(url, self.new_catalog_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
