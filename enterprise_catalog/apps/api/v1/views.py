from collections import OrderedDict

import crum
from celery import chain
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
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

from enterprise_catalog.apps.api.tasks import (
    index_enterprise_catalog_courses_in_algolia_task,
    update_catalog_metadata_task,
    update_full_content_metadata_task,
)
from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)
from enterprise_catalog.apps.api.v1.pagination import (
    PageNumberWithSizePagination,
)
from enterprise_catalog.apps.api.v1.serializers import (
    ContentMetadataSerializer,
    EnterpriseCatalogCreateSerializer,
    EnterpriseCatalogSerializer,
)
from enterprise_catalog.apps.api.v1.utils import unquote_course_keys
from enterprise_catalog.apps.catalog.algolia_utils import ALGOLIA_FIELDS
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog
from enterprise_catalog.apps.catalog.rules import (
    enterprises_with_admin_access,
    has_access_to_all_enterprises,
)


class BaseViewSet(PermissionRequiredMixin, viewsets.ViewSet):
    """
    Base class for all enterprise catalog view sets.
    """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]


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
        return enterprises_with_admin_access(self.request.user)

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
        if self.request_action == 'list':
            if not self.admin_accessible_enterprises:
                return EnterpriseCatalog.objects.none()
            if has_access_to_all_enterprises(self.admin_accessible_enterprises):
                return all_catalogs
            return all_catalogs.filter(enterprise_uuid__in=self.admin_accessible_enterprises)
        return all_catalogs


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
    def contains_content_items(self, request, uuid, course_run_ids, program_uuids, **kwargs):  # pylint: disable=unused-argument
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
    pagination_class = PageNumberWithSizePagination

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
        """
        enterprise_catalog = self.get_enterprise_catalog()
        # Avoids ordering the content metadata by any field on that model to avoid using a temporary table / filesort
        return enterprise_catalog.content_metadata.order_by('catalog_queries')

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
    def get_content_metadata(self, request, uuid, **kwargs):  # pylint: disable=unused-argument
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
    View to update metadata with data from the Discovery service and also index course metadata in Algolia.
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
        enterprise_catalog = get_object_or_404(EnterpriseCatalog, uuid=uuid)
        catalog_query_id = enterprise_catalog.catalog_query.id

        # Note: It's not immediately obvious, but there's some "auto-magic" passing of parameters through the
        # signatures used in the chain below. The return value of `update_catalog_metadata_task` (which should be a
        # list of content_keys that were updated) gets passed as the first value to the
        # `update_full_content_metadata_task`. The return value from that (which should be the list of content keys
        # that were updated with the full data from discovery) is likewise passed as the first argument to the
        # `index_enterprise_catalog_courses_in_algolia_task` (with the other args being whatever you actually put
        # inside the function call).
        # See https://docs.celeryproject.org/en/stable/userguide/canvas.html#the-primitives for more information on
        # partial chains.
        async_update_metadata_chain = chain(
            update_catalog_metadata_task.s(catalog_query_id),
            # Runs the `update_full_content_metadata_task` with the content keys that were associated in the
            # `update_catalog_metadata_task` to pad the metadata from discovery's /search/all endpoint with additional
            # data from the /courses endpoint
            update_full_content_metadata_task.si(),
            # Runs the indexing task with the indexable course keys that were returned from the
            # `update_full_content_metadata_task` to index those pieces of ContentMetadata in Algolia
            index_enterprise_catalog_courses_in_algolia_task.s(ALGOLIA_FIELDS),
        )
        async_task = async_update_metadata_chain.apply_async()

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
    def contains_content_items(self, request, enterprise_uuid, course_run_ids, program_uuids, **kwargs):  # pylint: disable=unused-argument
        """
        Returns whether or not the specified content is available for the given enterprise.
        ---
        parameters:
            - name: course_run_ids
              description: Ids of the course runs to check availability of
              paramType: query
            - name: program_uuids
              description: Uuids of the programs to check availability of
              paramType: query
            - name: get_catalog_list
              description: [Old parameter] Return a list of catalogs in which the course / program is present
              paramType: query
            - name: get_catalogs_containing_specified_content_ids
              description: Return a list of catalogs in which the course / program is present
              paramType: query
        """
        get_catalogs_containing_specified_content_ids = request.GET.get(
            'get_catalogs_containing_specified_content_ids', False
        )
        get_catalog_list = request.GET.get('get_catalog_list', False)
        course_run_ids = unquote_course_keys(course_run_ids)

        customer_catalogs = EnterpriseCatalog.objects.filter(enterprise_uuid=enterprise_uuid)
        any_catalog_contains_content_items = False
        catalogs_that_contain_course = []
        for catalog in customer_catalogs:
            contains_content_items = catalog.contains_content_keys(course_run_ids + program_uuids)
            if contains_content_items:
                any_catalog_contains_content_items = True
                if not (get_catalogs_containing_specified_content_ids or get_catalog_list):
                    # Break as soon as we find a catalog that contains the specified content
                    break
                catalogs_that_contain_course.append(catalog.uuid)

        response_data = {
            'contains_content_items': any_catalog_contains_content_items,
        }
        if (get_catalogs_containing_specified_content_ids or get_catalog_list):
            response_data['catalog_list'] = catalogs_that_contain_course
        return Response(response_data)


class DistinctCatalogQueriesView(APIView):
    """
    View that, given a list of EnterpriseCustomerCatalog UUIDs, returns the
    number of distinct EnterpriseCatalogQueries used by the given set of catalogs.

    Request Data:
        - enterprise_catalog_uuids (list[UUID4]): List of EnterpriseCustomerCatalog
        UUIDs to be used in a search for the number of distinct EnterpriseCatalogQuery
        objects used by the identified catalogs.

    Response Data:
        - count (int): number of distinct catalog queries used by given catalogs
        - catalog_query_ids (list[int]): IDs of the distinct catalog queries
    """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        """
        Method to handle POST requests to this endpoint
        """
        enterprise_catalog_uuids = request.data.get('enterprise_catalog_uuids', [])

        distinct_catalog_query_ids = EnterpriseCatalog.objects.filter(
            uuid__in=enterprise_catalog_uuids,
        ).distinct().values_list('catalog_query__id', flat=True)

        response_data = {
            'count': len(distinct_catalog_query_ids),
            'catalog_query_ids': distinct_catalog_query_ids,
        }
        return Response(response_data, status=HTTP_200_OK)
