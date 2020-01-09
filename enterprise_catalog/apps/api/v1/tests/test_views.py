from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from enterprise_catalog.apps.api.v1.views import EnterpriseCatalogViewSet
from enterprise_catalog.apps.catalog.tests.factories import (
    EnterpriseCatalogFactory,
    StaffUserFactory,
    UserFactory,
)


class EnterpriseCatalogViewSetTests(APITestCase):
    """
    Tests for the EnterpriseCatalogViewSet
    """
    def setUp(self):
        super(EnterpriseCatalogViewSetTests, self).setUp()
        self.enterprise_catalog = EnterpriseCatalogFactory()

    def test_get_unauthorized(self):
        """
        Verify the endpoint returns the details for a single enterprise catalog
        """
        import pdb; pdb.set_trace()
        url = reverse('api:v1:enterprise-catalog-detail', kwargs={'uuid': self.enterprise_catalog.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list(self):
        """
        Verify the endpoint returns a list of all enterprise catalogs
        """
        pass



