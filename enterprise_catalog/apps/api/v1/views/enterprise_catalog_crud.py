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
from edx_rbac.decorators import permission_required as permission_required_rbac

from functools import wraps
from rest_framework.exceptions import PermissionDenied
from django.utils.decorators import method_decorator

# temporarily added this decorator here
def has_permission_or_group(permission, group_name, fn=None):
    """
    Ensure that user has permission to access the endpoint OR is part of a group that has access.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            view = request.parser_context['view']
            action = view.action
            # Check for list action specific permissions
            pk = fn(request, **kwargs) if fn else kwargs.get('uuid')
            if pk:
                has_permission = user.has_perm(permission, pk)
            else:
                has_permission = user.has_perm(permission)
            
            if has_permission or user.groups.filter(name=group_name).exists():
                return view_func(request, *args, **kwargs)
            else:
                raise PermissionDenied(
                    "Access denied: Only admins and provisioning admins are allowed to access this endpoint.")
        return _wrapped_view
    return decorator


class EnterpriseCatalogCRUDViewSet(BaseViewSet, viewsets.ModelViewSet):
    """ Viewset for CRUD operations on Enterprise Catalogs """
    renderer_classes = [JSONRenderer, XMLRenderer]
    permission_required = []
    lookup_field = 'uuid'
    pagination_class = PageNumberWithSizePagination

    @cached_property
    def request_action(self):
        return getattr(self, 'action', None)

    def get_permission_required(self):
        """
        Return specific permission name based on the view being requested
        """
        return self.permission_required

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
        Retrieves the appropriate object to use during edx-rbac's permission checks.

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
    
    # @method_decorator(has_permission_or_group(permission='catalog.has_admin_access', group_name='test'))
    @permission_required_rbac('catalog.has_admin_access')
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    # @method_decorator(has_permission_or_group(permission='catalog.has_admin_access', group_name='test'))
    @permission_required_rbac('catalog.has_admin_access')
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    # @method_decorator(has_permission_or_group(permission='catalog.has_admin_access', group_name='test',fn=lambda request, uuid: uuid))
    @permission_required_rbac('catalog.has_admin_access')
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    # @method_decorator(has_permission_or_group(permission='catalog.has_admin_access', group_name='test))
    @permission_required_rbac('catalog.has_admin_access')
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    # @method_decorator(has_permission_or_group(permission='catalog.has_admin_access', group_name='test'))
    @permission_required_rbac('catalog.has_admin_access')
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    # @method_decorator(has_permission_or_group(permission='catalog.has_admin_access', group_name='test'))
    @permission_required_rbac('catalog.has_admin_access')
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
