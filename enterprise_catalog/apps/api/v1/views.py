from rest_framework import permissions, viewsets

from enterprise_catalog.apps.api.v1.serializers import (
    EnterpriseCatalogCreateSerializer,
    EnterpriseCatalogSerializer,
)
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


class EnterpriseCatalogViewSet(viewsets.ModelViewSet):
    """ View for CRUD operations on Enterprise Catalogs """
    serializer_class = EnterpriseCatalogSerializer
    queryset = EnterpriseCatalog.objects.all()
    permission_classes = [permissions.IsAdminUser]
    lookup_field = 'uuid'

    def get_serializer_class(self):
        action = getattr(self, 'action', None)
        if action == 'create':
            return EnterpriseCatalogCreateSerializer

        return EnterpriseCatalogSerializer
