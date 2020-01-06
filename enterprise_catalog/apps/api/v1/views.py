from django.shortcuts import get_object_or_404
from rest_framework.mixins import (
    ListModelMixin, RetrieveModelMixin, UpdateModelMixin
)
from rest_framework import viewsets
from rest_framework.response import Response

from enterprise_catalog.apps.api.v1.serializers import (
    CatalogQuerySerializer, EnterpriseCatalogSerializer, EnterpriseCatalogDetailSerializer
)
from enterprise_catalog.apps.catalog.models import CatalogQuery, EnterpriseCatalog


class EnterpriseCatalogViewSet(viewsets.ModelViewSet):
    """ TODO """
    queryset = EnterpriseCatalog.objects.all()

    def get_serializer_class(self):
        action = getattr(self, 'action', None)
        if action == 'retrieve':
            return EnterpriseCatalogDetailSerializer
        return EnterpriseCatalogSerializer
