"""
URL definitions for enterprise catalog API version 1.
"""
from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from enterprise_catalog.apps.api.v1 import views


app_name = 'v1'

router = DefaultRouter()
router.register(r'enterprise-catalogs', views.EnterpriseCatalogCRUDViewSet, basename='enterprise-catalog')
router.register(r'enterprise-catalogs', views.EnterpriseCatalogContainsContentItems, basename='enterprise-catalog')
router.register(r'enterprise-customer', views.EnterpriseCustomerViewSet, basename='enterprise-customer')

urlpatterns = [
    url(
        r'^enterprise-catalogs/catalog_csv_data',
        views.CatalogCsvDataView.as_view(),
        name='catalog-csv-data'
    ),
    url(
        r'^enterprise-catalogs/(?P<uuid>[\S]+)/get_content_metadata',
        views.EnterpriseCatalogGetContentMetadata.as_view({'get': 'get'}),
        name='get-content-metadata'
    ),
    url(
        r'^enterprise-catalogs/(?P<uuid>[\S]+)/generate_diff',
        views.EnterpriseCatalogDiff.as_view({'post': 'post'}),
        name='generate-catalog-diff'
    ),
    url(
        r'^enterprise-catalogs/(?P<uuid>[\S]+)/refresh_metadata',
        views.EnterpriseCatalogRefreshDataFromDiscovery.as_view({'post': 'post'}),
        name='update-enterprise-catalog'
    ),
    url(
        r'distinct-catalog-queries',
        views.DistinctCatalogQueriesView.as_view(),
        name='distinct-catalog-queries',
    ),
]

urlpatterns += router.urls
