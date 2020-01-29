# -*- coding: utf-8 -*-
"""
URL definitions for enterprise catalog API version 1.
"""
from __future__ import absolute_import, unicode_literals

from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from enterprise_catalog.apps.api.v1 import views


app_name = 'v1'

router = DefaultRouter()  # pylint: disable=invalid-name
router.register(r'enterprise-catalog', views.EnterpriseCatalogViewSet, basename='enterprise-catalog')
router.register(r'enterprise-customer', views.EnterpriseCustomerViewSet, basename='enterprise-customer')
# router.register(r'enterprise-catalog/(?P<uuid>[\S]+)/refresh_metadata', views.EnterpriseCatalogRefreshDataFromDiscovery, basename='update-enterprise-catalog')

urlpatterns = [
    url(
        r'^enterprise-catalog/(?P<uuid>[\S]+)/refresh_metadata',
        views.EnterpriseCatalogRefreshDataFromDiscovery.as_view(),
        name='update-enterprise-catalog'
    ),
]
urlpatterns += router.urls
