from rest_framework.reverse import reverse

from enterprise_catalog.apps.api.v1.tests.mixins import APITestMixin
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    ContentMetadata,
    EnterpriseCatalog,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    EnterpriseCatalogFactory,
)


class BaseEnterpriseCatalogViewSetTests(APITestMixin):
    """
    Base tests for EnterpriseCatalog view sets.
    """
    VERSION = 'v1'

    def setUp(self):
        super().setUp()
        # clean up any stale test objects
        CatalogQuery.objects.all().delete()
        ContentMetadata.objects.all().delete()
        EnterpriseCatalog.objects.all().delete()

        self.enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)

        # Set up catalog.has_learner_access permissions
        self.set_up_catalog_learner()

    def tearDown(self):
        super().tearDown()
        # clean up any stale test objects
        CatalogQuery.objects.all().delete()
        ContentMetadata.objects.all().delete()
        EnterpriseCatalog.objects.all().delete()

    def _get_contains_content_base_url(self, catalog_uuid=None):
        """
        Helper to construct the base url for the catalog contains_content_items endpoint
        """
        return reverse(
            f'api:{self.VERSION}:enterprise-catalog-content-contains-content-items',
            kwargs={'uuid': catalog_uuid or self.enterprise_catalog.uuid},
        )
