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


class BaseEnterpriseCustomerViewSetTests(APITestMixin):
    """
    Tests for the EnterpriseCustomerViewSet
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

    def _get_contains_content_base_url(self, enterprise_uuid=None):
        """
        Helper to construct the base url for the contains_content_items endpoint
        """
        return reverse(
            f'api:{self.VERSION}:enterprise-customer-contains-content-items',
            kwargs={'enterprise_uuid': enterprise_uuid or self.enterprise_uuid},
        )

    def _get_filter_content_base_url(self, enterprise_uuid=None):
        """
        Helper to construct the base url for the filter_content_items endpoint
        """
        return reverse(
            f'api:{self.VERSION}:enterprise-customer-filter-content-items',
            kwargs={'enterprise_uuid': enterprise_uuid or self.enterprise_uuid},
        )

    def _get_generate_diff_base_url(self, enterprise_catalog_uuid=None):
        """
        Helper to construct the base url for the catalog `generate_diff` endpoint
        """
        return reverse(
            f'api:{self.VERSION}:generate-catalog-diff',
            kwargs={'uuid': enterprise_catalog_uuid or self.enterprise_catalog.uuid},
        )

    def _get_content_metadata_base_url(self, enterprise_uuid, content_identifier):
        """
        Helper to construct the base url for the customer content metadata endpoint
        """
        return reverse(
            f'api:{self.VERSION}:customer-content-metadata-retrieve',
            kwargs={
                'enterprise_uuid': enterprise_uuid,
                'content_identifier': content_identifier,
            },
        )

    def _get_secured_algolia_api_key_base_url(self, enterprise_uuid):
        """
        Helper to construct the base url for the secured Algolia API key endpoint
        """
        return reverse(
            f'api:{self.VERSION}:enterprise-customer-secured-algolia-api-key',
            kwargs={
                'enterprise_uuid': enterprise_uuid,
            },
        )
