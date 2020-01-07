from rest_framework import viewsets

from enterprise_catalog.apps.api.v1.serializers import (
    EnterpriseCatalogSerializer,
    EnterpriseCatalogCreateSerializer,
)
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


class EnterpriseCatalogViewSet(viewsets.ModelViewSet):
    """ View for CRUD operations on Enterprise Catalogs """
    serializer_class = EnterpriseCatalogSerializer
    queryset = EnterpriseCatalog.objects.all()

    def get_serializer_class(self):
        action = getattr(self, 'action', None)
        if action == 'create':
            return EnterpriseCatalogCreateSerializer

        return EnterpriseCatalogSerializer
