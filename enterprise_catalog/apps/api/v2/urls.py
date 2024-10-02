"""
URL definitions for enterprise catalog API version 1.
"""
from django.urls import path, re_path
from rest_framework.routers import DefaultRouter

from enterprise_catalog.apps.api.v2.views.enterprise_catalog_contains_content_items import (
    EnterpriseCatalogContainsContentItems,
)
from enterprise_catalog.apps.api.v2.views.enterprise_catalog_get_content_metadata import (
    EnterpriseCatalogGetContentMetadata,
)
from enterprise_catalog.apps.api.v2.views.enterprise_customer import (
    EnterpriseCustomerViewSet,
)


app_name = 'v2'

router = DefaultRouter()
router.register(r'enterprise-catalogs', EnterpriseCatalogContainsContentItems, basename='enterprise-catalog-content-v2')
router.register(r'enterprise-customer', EnterpriseCustomerViewSet, basename='enterprise-customer-v2')

urlpatterns = [
    re_path(
        r'^enterprise-catalogs/(?P<uuid>[\S]+)/get_content_metadata',
        EnterpriseCatalogGetContentMetadata.as_view({'get': 'get'}),
        name='get-content-metadata-v2'
    ),
    path(
        'enterprise-customer/<enterprise_uuid>/content-metadata/<content_identifier>/',
        EnterpriseCustomerViewSet.as_view({'get': 'content_metadata'}),
        name='customer-content-metadata-retrieve-v2'
    ),
]

urlpatterns += router.urls
