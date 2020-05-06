from collections import OrderedDict

import crum
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from edx_rbac.mixins import PermissionRequiredMixin
from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.views import APIView
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.tasks import update_catalog_metadata_task
from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)
from enterprise_catalog.apps.api.v1.serializers import (
    ContentMetadataSerializer,
    EnterpriseCatalogCreateSerializer,
    EnterpriseCatalogSerializer,
)
from enterprise_catalog.apps.api.v1.utils import unquote_course_keys
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


class BaseViewSet(PermissionRequiredMixin, viewsets.ViewSet):
    """
    Base class for all enterprise catalog view sets.
    """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]


class EnterpriseCatalogCRUDViewSet(BaseViewSet, viewsets.ModelViewSet):
    """ Viewset for CRUD operations on Enterprise Catalogs """
    queryset = EnterpriseCatalog.objects.all().order_by('created')
    renderer_classes = [JSONRenderer, XMLRenderer]
    permission_required = 'catalog.has_admin_access'
    lookup_field = 'uuid'

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
        request_action = getattr(self, 'action', None)
        if request_action == 'create':
            request = crum.get_current_request()
            return request.data.get('enterprise_customer', None)
        elif request_action == 'list':
            # `django-rules` only supports object-level permissions, i.e. does not filter the
            # objects in querysets; returning `None` here forces the permissions check to fail.
            return None
        if self.kwargs.get('uuid'):
            enterprise_catalog = self.get_object()
            return str(enterprise_catalog.enterprise_uuid)
        return None


class EnterpriseCatalogContainsContentItems(BaseViewSet, viewsets.ModelViewSet):
    """
    View to determine if an enterprise catalog contains certain content
    """
    queryset = EnterpriseCatalog.objects.all().order_by('created')
    renderer_classes = [JSONRenderer, XMLRenderer]
    serializer_class = EnterpriseCatalogSerializer
    permission_required = 'catalog.has_learner_access'
    lookup_field = 'uuid'

    def get_permission_object(self):
        """
        Retrieves the apporpriate object to use during edx-rbac's permission checks.

        This object is passed to the rule predicate(s).
        """
        if self.kwargs.get('uuid'):
            enterprise_catalog = self.get_object()
            return str(enterprise_catalog.enterprise_uuid)
        return None

    @method_decorator(require_at_least_one_query_parameter('course_run_ids', 'program_uuids'))
    @action(detail=True)
    def contains_content_items(self, request, uuid, course_run_ids, program_uuids, **kwargs):
        """
        Returns whether or not the EnterpriseCatalog contains the specified content.

        Multiple course_run_ids and/or program_uuids query parameters can be sent to this view to check for their
        existence in the specified enterprise catalog.
        """
        course_run_ids = unquote_course_keys(course_run_ids)

        enterprise_catalog = self.get_object()
        contains_content_items = enterprise_catalog.contains_content_keys(course_run_ids + program_uuids)
        return Response({'contains_content_items': contains_content_items})


class EnterpriseCatalogGetContentMetadata(BaseViewSet, GenericAPIView):
    """
    View for retrieving all the content metadata associated with a catalog.
    """
    permission_required = 'catalog.has_learner_access'
    serializer_class = ContentMetadataSerializer
    renderer_classes = [JSONRenderer, XMLRenderer]
    lookup_field = 'uuid'

    def get_enterprise_catalog(self):
        """
        Helper for retrieving the specified enterprise catalog, or 404ing if it doesn't exist.
        """
        uuid = self.kwargs.get('uuid')
        return get_object_or_404(EnterpriseCatalog, uuid=uuid)

    def get_permission_object(self):
        """
        Retrieves the apporpriate object to use during edx-rbac's permission checks.

        This object is passed to the rule predicate(s).
        """
        enterprise_catalog = self.get_enterprise_catalog()
        return str(enterprise_catalog.enterprise_uuid)

    def get_queryset(self):
        """
        Returns all of the json of content metadata associated with the catalog.

        Note that the metadata is ordered by content key.
        """
        enterprise_catalog = self.get_enterprise_catalog()
        ordered_metadata = enterprise_catalog.content_metadata.order_by('content_key')
        return ordered_metadata

    def get_response_with_enterprise_fields(self, response):
        """
        Add on the enterprise fields to the top level of the DRF response

        Args:
            response (HttpResponse): The existing DRF response to add on to

        Returns:
            HttpResponse: The new response with additional fields added on
        """
        enterprise_catalog = self.get_enterprise_catalog()
        response.data['uuid'] = enterprise_catalog.uuid
        response.data['title'] = enterprise_catalog.title
        response.data['enterprise_customer'] = enterprise_catalog.enterprise_uuid
        response.data.move_to_end('results')  # Place the results at the end of the response again
        return response

    @action(detail=True)
    def get_content_metadata(self, request, uuid, **kwargs):
        """
        Returns all the content metadata associated with the enterprise catalog.

        Adding the query parameter `traverse_pagination` will collect the results onto a single page.
        """
        queryset = self.filter_queryset(self.get_queryset())
        enterprise_catalog = self.get_enterprise_catalog()
        context = self.get_serializer_context()
        context['enterprise_catalog'] = enterprise_catalog
        # Traverse pagination query parameter signals that we should collect the results onto a single page
        traverse_pagination = request.query_params.get('traverse_pagination', False)
        page = self.paginate_queryset(queryset)
        if page is not None and not traverse_pagination:
            serializer = ContentMetadataSerializer(page, context=context, many=True)
            paginated_response = self.get_paginated_response(serializer.data)
            return self.get_response_with_enterprise_fields(paginated_response)

        serializer = ContentMetadataSerializer(queryset, context=context, many=True)
        ordered_data = OrderedDict({
            'previous': None,
            'next': None,
            'count': len(queryset),
            'results': serializer.data,
        })
        response = Response(ordered_data)
        return self.get_response_with_enterprise_fields(response)


class EnterpriseCatalogRefreshDataFromDiscovery(BaseViewSet, APIView):
    """
    View to update metadata in Catalog with most recent data from Discovery service
    """
    permission_required = 'catalog.has_admin_access'

    def get_permission_object(self):
        """
        Retrieves the apporpriate object to use during edx-rbac's permission checks.

        This object is passed to the rule predicate(s).
        """
        uuid = self.kwargs.get('uuid')
        enterprise_catalog = get_object_or_404(EnterpriseCatalog, uuid=uuid)
        return str(enterprise_catalog.enterprise_uuid)

    def post(self, request, uuid):
        async_task = update_catalog_metadata_task.delay(catalog_uuid=uuid)
        return Response({'async_task_id': async_task.task_id}, status=HTTP_200_OK)


class EnterpriseCustomerViewSet(BaseViewSet):
    """
    Viewset for operations on enterprise customers.

    Although we don't have a specific EnterpriseCustomer model, this viewset handles operations that use an enterprise
    identifier to perform operations on their associated catalogs, etc.
    """
    permission_required = 'catalog.has_learner_access'
    # Just a convenience so that `enterprise_uuid` becomes an argument on our detail routes
    lookup_field = 'enterprise_uuid'

    def get_permission_object(self):
        """
        Retrieves the apporpriate object to use during edx-rbac's permission checks.

        This object is passed to the rule predicate(s).
        """
        return self.kwargs.get('enterprise_uuid')

    @method_decorator(require_at_least_one_query_parameter('course_run_ids', 'program_uuids'))
    @action(detail=True)
    def contains_content_items(self, request, enterprise_uuid, course_run_ids, program_uuids, **kwargs):
        """
        Returns whether or not the specified content is available for the given enterprise.
        """
        course_run_ids = unquote_course_keys(course_run_ids)

        customer_catalogs = EnterpriseCatalog.objects.filter(enterprise_uuid=enterprise_uuid)
        contains_content_items = False
        for catalog in customer_catalogs:
            contains_content_items = catalog.contains_content_keys(course_run_ids + program_uuids)
            # Break as soon as we find a catalog that contains the specified content
            if contains_content_items:
                break

        return Response({'contains_content_items': contains_content_items})
