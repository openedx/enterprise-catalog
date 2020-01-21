from edx_rbac.mixins import PermissionRequiredMixin
from edx_rest_framework_extensions.auth.bearer.authentication import (
    BearerAuthentication,
)
from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication

from enterprise_catalog.apps.api.v1.serializers import (
    EnterpriseCatalogCreateSerializer,
    EnterpriseCatalogSerializer,
)
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


# class EnterpriseCatalogViewSet(viewsets.ModelViewSet):
class EnterpriseCatalogViewSet(PermissionRequiredMixin, viewsets.ModelViewSet):
    """ View for CRUD operations on Enterprise Catalogs """
    serializer_class = EnterpriseCatalogSerializer
    queryset = EnterpriseCatalog.objects.all().order_by('created')
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    authentication_classes = [JwtAuthentication, BearerAuthentication, SessionAuthentication]
    permission_required = 'enterprise.can_view_catalog'
    lookup_field = 'uuid'

    def get_serializer_class(self):
        action = getattr(self, 'action', None)
        if action == 'create':
            return EnterpriseCatalogCreateSerializer

        return EnterpriseCatalogSerializer
