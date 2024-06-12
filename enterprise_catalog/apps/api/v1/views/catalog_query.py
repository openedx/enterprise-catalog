from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from edx_rbac.mixins import PermissionRequiredForListingMixin
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)
from enterprise_catalog.apps.api.v1.serializers import (
    CatalogQueryGetByHashRequestSerializer,
    CatalogQuerySerializer,
)
from enterprise_catalog.apps.api.v1.views.base import BaseViewSet
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    EnterpriseCatalog,
    EnterpriseCatalogRoleAssignment,
)
from enterprise_catalog.apps.catalog.rules import (
    enterprises_with_admin_access,
    has_access_to_all_enterprises,
)


class CatalogQueryViewSet(viewsets.ReadOnlyModelViewSet, BaseViewSet, PermissionRequiredForListingMixin):
    """Read-only viewset for Catalog Query records"""
    renderer_classes = [JSONRenderer]
    serializer_class = CatalogQuerySerializer
    permission_required = 'catalog.has_admin_access'
    list_lookup_field = 'enterprise_catalogs__enterprise_uuid'
    role_assignment_class = EnterpriseCatalogRoleAssignment

    @property
    def base_queryset(self):
        """
        Required by the `PermissionRequiredForListingMixin`.
        For non-list actions, this is what's returned by `get_queryset()`.
        For list actions, some non-strict subset of this is what's returned by `get_queryset()`.
        """
        return CatalogQuery.objects.all()

    @cached_property
    def admin_accessible_enterprises(self):
        """
        Cached set of enterprise identifiers the requesting user has admin access to.
        """
        return enterprises_with_admin_access(self.request)

    def get_queryset(self):
        """
        Restrict the queryset to catalog queries the requesting user has access to. Iff the user is staff they have
        access to all queries.
        """
        all_queries = self.base_queryset
        if not self.admin_accessible_enterprises:
            return CatalogQuery.objects.none()
        if has_access_to_all_enterprises(self.admin_accessible_enterprises) or self.request.user.is_staff:
            return all_queries
        return all_queries.filter(
            enterprise_catalogs__enterprise_uuid__in=self.admin_accessible_enterprises
        )

    def check_permissions(self, request):
        """
        If dealing with a "list" action, goes through some customized
        logic to check which contexts are accessible by the requesting
        user.  If none are, and the user is not staff/super, raise
        a `PermissionDenied` exception.  Uses the parent class's `check_permissions()`
        method if the request action is not "list".
        """
        if request.user.is_staff and self.staff_are_never_forbidden:
            return
        if request.user.is_superuser:
            return
        if self.request_action == 'list':
            if not self.accessible_contexts:
                self.permission_denied(request)
        else:
            related_catalog_uuids = [
                str(cat.enterprise_uuid) for cat in EnterpriseCatalog.objects.filter(
                    catalog_query__in=self.get_queryset()
                )
            ]
            allowed_contexts = self.admin_accessible_enterprises
            if set(related_catalog_uuids).intersection(allowed_contexts):
                return
            self.permission_denied(request)

    @method_decorator(require_at_least_one_query_parameter('hash'))
    @action(detail=True, methods=['get'])
    def get_query_by_hash(self, request, **kwargs):
        """
        Fetch a Catalog Query by its hash. The hash values are a product of Python's ``hashlib``'s md5 algorithm
        in hexdigest representation.
        """
        request_serializer = CatalogQueryGetByHashRequestSerializer(data=request.query_params)
        request_serializer.is_valid(raise_exception=True)
        content_filter_hash = request_serializer.validated_data.get('hash')
        try:
            query = self.get_queryset().get(content_filter_hash=content_filter_hash)
        except CatalogQuery.DoesNotExist as exc:
            raise NotFound('Catalog query not found.') from exc
        serialized_data = self.serializer_class(query)
        return Response(serialized_data.data)
