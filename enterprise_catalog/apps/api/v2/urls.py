"""
URL definitions for enterprise catalog API version 2.
"""
from django.urls import path, re_path
from rest_framework.routers import DefaultRouter

from enterprise_catalog.apps.api.v2.views.enterprise_catalog_get_content_metadata import (
    EnterpriseCatalogGetContentMetadataV2,
)


app_name = 'v2'

router = DefaultRouter()

urlpatterns = [
    re_path(
        r'^enterprise-catalogs/(?P<uuid>[\S]+)/get_content_metadata',
        EnterpriseCatalogGetContentMetadataV2.as_view({'get': 'get'}),
        name='get-content-metadata-v2'
    ),
]

urlpatterns += router.urls
