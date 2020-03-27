# -*- coding: utf-8 -*-
"""
URL definitions for enterprise catalog API version 1.
"""
from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from enterprise_catalog.apps.api.v1 import views


app_name = 'v1'

router = DefaultRouter()  # pylint: disable=invalid-name
router.register(r'enterprise-catalogs', views.EnterpriseCatalogCRUDViewSet, basename='enterprise-catalog')
router.register(r'enterprise-catalogs', views.EnterpriseCatalogActionViewSet, basename='enterprise-catalog')
router.register(r'enterprise-customer', views.EnterpriseCustomerViewSet, basename='enterprise-customer')

urlpatterns = [
    url(
        r'^enterprise-catalogs/(?P<uuid>[\S]+)/refresh_metadata',
        views.EnterpriseCatalogRefreshDataFromDiscovery.as_view({'post': 'post'}),
        name='update-enterprise-catalog'
    ),
]

urlpatterns += router.urls
