"""
URL definitions for enterprise catalog API version 2.
"""
from django.urls import path, re_path
from rest_framework.routers import DefaultRouter

from enterprise_catalog.apps.api.v2.views.enterprise_catalog_contains_content_items import (
    EnterpriseCatalogContainsContentItemsV2,
)
from enterprise_catalog.apps.api.v2.views.enterprise_catalog_get_content_metadata import (
    EnterpriseCatalogGetContentMetadataV2,
)
from enterprise_catalog.apps.api.v2.views.enterprise_customer import (
    EnterpriseCustomerViewSetV2,
)


app_name = 'v2'

router = DefaultRouter()
router.register(r'enterprise-catalogs', EnterpriseCatalogContainsContentItemsV2, basename='enterprise-catalog-content-v2')
router.register(r'enterprise-customer', EnterpriseCustomerViewSetV2, basename='enterprise-customer-v2')

urlpatterns = [
    re_path(
        r'^enterprise-catalogs/(?P<uuid>[\S]+)/get_content_metadata',
        EnterpriseCatalogGetContentMetadataV2.as_view({'get': 'get'}),
        name='get-content-metadata-v2'
    ),
    path(
        'enterprise-customer/<enterprise_uuid>/content-metadata/<content_identifier>/',
        EnterpriseCustomerViewSetV2.as_view({'get': 'content_metadata'}),
        name='customer-content-metadata-retrieve-v2'
    ),
]

urlpatterns += router.urls
