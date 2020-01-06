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


class EnterpriseCatalogViewSet(viewsets.ViewSet):
    """ TODO """
    def list(self, request):
        queryset = EnterpriseCatalog.objects.all()
        serializer = EnterpriseCatalogSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        queryset = EnterpriseCatalog.objects.all()
        enterprise_catalog = get_object_or_404(queryset, pk=pk)
        serializer = EnterpriseCatalogDetailSerializer(enterprise_catalog)
        return Response(serializer.data)
