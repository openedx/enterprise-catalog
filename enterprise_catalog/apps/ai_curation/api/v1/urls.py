"""
URL definitions for AI Curations API version 1.
"""
from django.urls import path

from enterprise_catalog.apps.ai_curation.api.v1.views import AICurationView


urlpatterns = [
    path('ai-curation', AICurationView.as_view(), name='ai-curation'),
]
