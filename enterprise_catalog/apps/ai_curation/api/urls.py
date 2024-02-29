"""
URL definitions for AI Curations API.
"""
from django.urls import include, path

from enterprise_catalog.apps.ai_curation.api.v1 import urls as v1_urls


app_name = 'ai_curation'
urlpatterns = [
    path('v1/', include(v1_urls)),
]
