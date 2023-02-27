import crum
from django.utils.functional import cached_property
from rest_framework import viewsets
from rest_framework.renderers import JSONRenderer
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.v1.pagination import (
    PageNumberWithSizePagination,
)
from enterprise_catalog.apps.api.v1.serializers import (
    EnterpriseCatalogCreateSerializer,
    EnterpriseCatalogSerializer,
)
from enterprise_catalog.apps.api.v1.views.base import BaseViewSet
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog
from enterprise_catalog.apps.catalog.rules import (
    enterprises_with_admin_access,
    has_access_to_all_enterprises,
)


class EnterpriseCatalogCRUDViewSet(BaseViewSet, viewsets.ModelViewSet):
    """ Viewset for CRUD operations on Enterprise Catalogs """
    renderer_classes = [JSONRenderer, XMLRenderer]
    permission_required = 'catalog.has_admin_access'
    lookup_field = 'uuid'
    pagination_class = PageNumberWithSizePagination

    @cached_property
    def request_action(self):
        return getattr(self, 'action', None)

    @cached_property
    def admin_accessible_enterprises(self):
        """
        Cached set of enterprise identifiers the requesting user has admin access to.
        """
        return enterprises_with_admin_access(self.request)

    def get_serializer_class(self):
        request_action = getattr(self, 'action', None)
        if request_action == 'create':
            return EnterpriseCatalogCreateSerializer
        return EnterpriseCatalogSerializer

    def get_permission_object(self):
        """
        Retrieves the apporpriate object to use during edx-rbac's permission checks.

        This object is passed to the rule predicate(s).
        """
        if self.request_action == 'create':
            request = crum.get_current_request()
            return request.data.get('enterprise_customer', None)
        if self.kwargs.get('uuid'):
            enterprise_catalog = self.get_object()
            return str(enterprise_catalog.enterprise_uuid)
        return None

    def check_permissions(self, request):
        """
        Check through permissions required and throws a permission_denied if missing any.

        If `get_permission_object` is implemented, it will be called and should return the object
        for which the `rules` predicate checks against.
        """
        if self.request_action == 'list':
            # Super-users and staff won't get Forbidden responses,
            # but depending on their assigned roles, staff may
            # get an empty result set.
            if request.user.is_staff:
                return
            if not self.admin_accessible_enterprises:
                self.permission_denied(request)
        else:
            super().check_permissions(request)

    def get_queryset(self):
        """
        Returns the queryset corresponding to all catalogs the requesting user has access to.
        """
        all_catalogs = EnterpriseCatalog.objects.all().order_by('created')
        enterprise_customer = self.request.GET.get('enterprise_customer', False)
        if enterprise_customer:
            all_catalogs = all_catalogs.filter(enterprise_uuid=enterprise_customer)

        if self.request_action == 'list':
            if not self.admin_accessible_enterprises:
                return EnterpriseCatalog.objects.none()
            if has_access_to_all_enterprises(self.admin_accessible_enterprises):
                return all_catalogs
            return all_catalogs.filter(enterprise_uuid__in=self.admin_accessible_enterprises)
        return all_catalogs
