from rest_framework.test import APITestCase

from enterprise_catalog.apps.catalog.tests.factories import (
    USER_PASSWORD,
    UserFactory,
)


class APITestMixin(APITestCase):
    """
    Mixin for functions shared between different API test classes
    """

    def setUp(self):
        super(APITestMixin, self).setUp()
        self.user = UserFactory(is_staff=True)
        self.client.login(username=self.user.username, password=USER_PASSWORD)

    def set_up_non_staff(self):
        """
        Helper for logging in as a non-staff user
        """
        self.client.logout()
        non_staff_user = UserFactory()
        self.client.login(username=non_staff_user.username, password=USER_PASSWORD)

    def assert_correct_contains_response(self, url, expected_value):
        """
        Helper to assert that the contains_content_items endpoint specified by the url returns the correct value
        """
        response = self.client.get(url)
        self.assertEqual(response.json()['contains_content_items'], expected_value)

    def add_metadata_to_catalog(self, catalog, metadata):
        """
        Adds the given pieces of metadata to a catalog

        Args:
            catalog (EnterpriseCatalog): Enterprise catalog to associate the metadata with
            metadata (iterable of ContentMetadata): Iterable of 1 or more pieces of ContentMetadata to add to a catalog
        """
        catalog.catalog_query.contentmetadata_set.add(*metadata)
