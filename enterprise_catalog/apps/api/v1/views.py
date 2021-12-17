import csv
import datetime
import logging
from collections import OrderedDict, defaultdict
from io import StringIO

import crum
from celery import chain
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from edx_rbac.mixins import PermissionRequiredMixin
from edx_rbac.utils import get_decoded_jwt
from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import GenericAPIView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST
from rest_framework.views import APIView
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.tasks import (
    index_enterprise_catalog_in_algolia_task,
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
from enterprise_catalog.apps.catalog.algolia_utils import (
    ALGOLIA_INDEX_SETTINGS,
    get_initialized_algolia_client,
)
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog
from enterprise_catalog.apps.catalog.rules import (
    enterprises_with_admin_access,
    has_access_to_all_enterprises,
)


logger = logging.getLogger(__name__)


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


class CatalogCsvDataView(GenericAPIView):
    """
    Catalog CSV data generation view. All query params are assumed to be facet filters used to filter indexed data when
    searching. All distinct facets provided are interpreted as a conjunction (AND), however multiple identical facets
    query params use a disjunction (OR).

    Returns:
        string IO stream representation of CSV data correlating to filtered Algolia catalog metadata.
    """
    permission_classes = []
    csv_headers = [
        'Title',
        'Partner Name',
        'Start',
        'End',
        'Verified Upgrade Deadline',
        'Program Type',
        'Program Name',
        'Pacing',
        'Level',
        'Price',
        'Language',
        'URL',
        'Short Description',
        'Subjects',
        'Key',
        'Short Key',
        'Skills',
    ]
    algolia_attributes_to_retrieve = [
        'title',
        'partners',
        'advertised_course_run',
        'programs',
        'program_titles',
        'level_type',
        'language',
        'short_description',
        'subjects',
        'aggregation_key',
        'skills',
        'first_enrollable_paid_seat_price',
        'marketing_url',
    ]
    valid_facets = []
    for facet in ALGOLIA_INDEX_SETTINGS['attributesForFaceting']:
        # Because this is pulled from the settings `attributesForFaceting`, we need to strip potential `searchable()`
        # wrappers
        valid_facets.append(facet.replace('searchable(', '').rstrip(')'))

    @action(detail=True)
    def get(self, request, **kwargs):
        """
        GET entry point for the `CatalogCsvDataView`
        """
        facets = self.querydict_to_dict(request.query_params)
        if facets.get('query'):
            algoliaQuery = facets.pop('query')
        else:
            algoliaQuery = ''

        invalid_facets = self.validate_query_facets(facets)
        if invalid_facets:
            return Response(f'Error: invalid facet(s): {invalid_facets} provided.', status=HTTP_400_BAD_REQUEST)

        csv_data = self.retrieve_indexed_data(facets, algoliaQuery)
        return Response({'csv_data': csv_data}, status=HTTP_200_OK)

    def validate_query_facets(self, facets):
        """
        Verify that provided query facet params are valid Algolia facets.
        """
        invalid_facets = []
        for facet in facets.keys():
            if facet not in self.valid_facets:
                invalid_facets.append(facet)
        return invalid_facets

    def querydict_to_dict(self, query_dict):
        """
        Utility function to easily retrieve lists from the params in a QueryDict
        """
        data = {}
        for key in query_dict.keys():
            v = query_dict.getlist(key)
            data[key] = v
        return data

    def construct_csv_row(self, hit):
        """
        Helper function to construct a CSV row according to a single Algolia result hit.
        """
        csv_row = []
        csv_row.append(hit.get('title', 'No title'))

        if hit.get('partners'):
            csv_row.append(hit['partners'][0]['name'])
        else:
            csv_row.append('No partners')

        if hit.get('advertised_course_run'):
            csv_row.append(hit['advertised_course_run']['start'])

            end = hit['advertised_course_run'].get('end')
            if not end:
                end = 'No end date'
            csv_row.append(end)

            upgrade_deadline = hit['advertised_course_run'].get('upgrade_deadline')
            if upgrade_deadline:
                upgrade_deadline = datetime.datetime.fromtimestamp(upgrade_deadline)
            else:
                upgrade_deadline = 'No upgrade deadline'
            csv_row.append(upgrade_deadline)

            pacing_type = hit['advertised_course_run']['pacing_type']
            key = hit['advertised_course_run'].get('key', 'No key')
        else:
            csv_row.append('No start date')
            csv_row.append('No end date')
            csv_row.append('No upgrade deadline')
            pacing_type = None
            key = 'No key'

        programs = hit.get('programs')
        if not programs:
            programs = 'No program'
        csv_row.append(programs)

        program_titles = hit.get('program_titles')
        if not program_titles:
            program_titles = 'No program'
        csv_row.append(program_titles)

        if not pacing_type:
            pacing_type = 'No pacing type'
        csv_row.append(pacing_type)

        csv_row.append(hit.get('level_type', 'No level_type'))

        csv_row.append(hit.get('first_enrollable_paid_seat_price', 'No price'))
        csv_row.append(hit.get('language', 'No language'))
        csv_row.append(hit.get('marketing_url', 'No url'))
        csv_row.append(hit.get('short_description', 'No short description'))

        csv_row.append(str(hit.get('subjects', 'No subjects')))
        csv_row.append(key)
        csv_row.append(hit.get('aggregation_key', 'No aggregation key'))

        skills = [skill['name'] for skill in hit.get('skills', [])]
        csv_row.append(str(skills))
        return csv_row

    def retrieve_indexed_data(self, facets, algoliaQuery):
        """
        Helper function to retrieve and format indexed Algolia data into a CSV format.
        """
        algolia_client = get_initialized_algolia_client()

        facet_filters = []
        for facet_name, facet_values in facets.items():
            combined_facets = []
            for facet_value in facet_values:
                combined_facets.append(f'{facet_name}:{facet_value}')
            facet_filters.append(combined_facets)

        # Algolia search will only retrieve all results if you query by empty string.
        algolia_hits = algolia_client.algolia_index.browse_objects({
            'query': algoliaQuery,
            'facetFilters': facet_filters,
            'attributesToRetrieve': self.algolia_attributes_to_retrieve
        })
        with StringIO() as file:
            writer = csv.writer(file)
            writer.writerow(self.csv_headers)
            for hit in algolia_hits:
                row = self.construct_csv_row(hit)
                writer.writerow(row)
            return file.getvalue()


class EnterpriseCatalogDiff(BaseViewSet, viewsets.ModelViewSet):
    """
    View to determine if an enterprise catalog contains certain content
    """
    queryset = EnterpriseCatalog.objects.all().order_by('created')
    renderer_classes = [JSONRenderer, XMLRenderer]
    serializer_class = EnterpriseCatalogSerializer
    permission_required = 'catalog.has_learner_access'
    lookup_field = 'uuid'
    MAX_GET_CONTENT_KEYS = 100

    def get_permission_object(self):
        """
        Retrieves the appropriate object to use during edx-rbac's permission checks.

        This object is passed to the rule predicate(s).
        """
        if self.kwargs.get('uuid'):
            enterprise_catalog = self.get_object()
            return str(enterprise_catalog.enterprise_uuid)
        return None

    @action(detail=True)
    def post(self, request, **kwargs):
        content_keys = []
        if request.data:
            content_keys = request.data.get('content_keys')
        return self.catalog_diff(content_keys)

    @method_decorator(require_at_least_one_query_parameter('content_keys'))
    @action(detail=True)
    def get(self, request, content_keys, **kwargs):
        if content_keys == "[]":
            content_keys = []
        else:
            if len(content_keys) > self.MAX_GET_CONTENT_KEYS:
                return Response(
                    f'catalog_diff GET requests supports up to {self.MAX_GET_CONTENT_KEYS}. If more content keys '
                    f'required, please use a POST body.',
                    status=HTTP_400_BAD_REQUEST
                )

        return self.catalog_diff(content_keys)

    def catalog_diff(self, content_keys):
        """
        Generate three buckets representing a diff between a list of content keys and what content exists under a
        catalog

        Params:
            content_keys: (list) A list of content key strings representing content under a catalog

        Response buckets:
            'items_not_found': A list of all content keys that were provided in the content_keys param that were not
            found under the catalog.
            'items_not_included': A list of sets of content keys that were found under the catalog but not provided in
            the content_keys param.
            'items_found': A list of dicts containing 'content_key's and 'date_updated' of content keys provided in the
            content_keys param that were found under the catalog.
        """
        content_keys = unquote_course_keys(content_keys)
        enterprise_catalog = self.get_object()
        items_not_found, items_not_included, items_found = enterprise_catalog.get_catalog_content_diff(content_keys)
        return Response({
            'items_not_found': items_not_found,
            'items_not_included': items_not_included,
            'items_found': items_found
        })


class EnterpriseCatalogGetContentMetadata(BaseViewSet, GenericAPIView):
    """
    View for retrieving all the content metadata associated with a catalog.
    """
    permission_required = 'catalog.has_learner_access'
    serializer_class = ContentMetadataSerializer
    renderer_classes = [JSONRenderer, XMLRenderer]
    lookup_field = 'uuid'
    pagination_class = PageNumberWithSizePagination
    MAX_GET_CONTENT_KEYS = 100

    @cached_property
    def enterprise_catalog(self):
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
        return str(self.enterprise_catalog.enterprise_uuid)

    def get_queryset(self, **kwargs):
        """
        Returns all of the json of content metadata associated with the catalog.
        """
        # Avoids ordering the content metadata by any field on that model to avoid using a temporary table / filesort
        queryset = self.enterprise_catalog.content_metadata
        content_filter = kwargs.get('content_keys_filter')
        if content_filter:
            queryset = queryset.filter(content_key__in=content_filter)

        return queryset.order_by('catalog_queries')

    def get_response_with_enterprise_fields(self, response):
        """
        Add on the enterprise fields to the top level of the DRF response

        Args:
            response (HttpResponse): The existing DRF response to add on to

        Returns:
            HttpResponse: The new response with additional fields added on
        """
        response.data['uuid'] = self.enterprise_catalog.uuid
        response.data['title'] = self.enterprise_catalog.title
        response.data['enterprise_customer'] = self.enterprise_catalog.enterprise_uuid
        response.data.move_to_end('results')  # Place the results at the end of the response again
        return response

    @action(detail=True)
    def get(self, request, **kwargs):
        """
        GET view entry point to the `get_content_metadata` API

        Query params:
            (Optional) content_keys (list): list of content keys for which to fetch content metadata for. If no content
            keys are provided then all content under the catalog will be fetched.
        """
        content_keys_filter = request.query_params.getlist('content_keys')
        if content_keys_filter == "[]":
            content_keys_filter = []
        else:
            if len(content_keys_filter) > self.MAX_GET_CONTENT_KEYS:
                return Response(
                    f'get_content_metadata GET requests supports up to {self.MAX_GET_CONTENT_KEYS}. If more content'
                    f'keys required, please use a POST body.',
                    status=HTTP_400_BAD_REQUEST
                )

        traverse_pagination = request.query_params.get('traverse_pagination', False)

        return self.get_content_metadata(request, traverse_pagination, content_keys_filter)

    @action(detail=True)
    def get_content_metadata(self, request, traverse_pagination, content_keys_filter):
        """
        Returns all the content metadata associated with the enterprise catalog.

        The parameter `traverse_pagination`, if provided, will collect the results onto a single page.

        The parameter `content_keys_filter`, if provided, will result in only content metadata associated with the
        provided content keys being returned.
        """
        queryset = self.filter_queryset(self.get_queryset(content_keys_filter=content_keys_filter))
        context = self.get_serializer_context()
        context['enterprise_catalog'] = self.enterprise_catalog
        page = self.paginate_queryset(queryset)

        # Traverse pagination query parameter signals that we should collect the results onto a single page
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

        # Use immutable signatures so task results from a parent task are not passed as arguments to a child task.
        async_update_metadata_chain = chain(
            update_catalog_metadata_task.si(catalog_query_id),
            update_full_content_metadata_task.si(),
            index_enterprise_catalog_in_algolia_task.si(),
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

    def check_permissions(self, request):
        """
        Helper to log information from Auth token on
        PermissionDenied errors.
        See https://openedx.atlassian.net/browse/ENT-4885
        """
        try:
            super().check_permissions(request)
        except PermissionDenied:
            decoded_jwt = get_decoded_jwt(request)
            message = (
                'PermissionDenied for user_id (from JWT) %s and EnterpriseCustomer %s in '
                'contains_content_items. JWT roles: %s',
            )
            logger.exception(
                message,
                decoded_jwt.get('user_id'),
                self.kwargs.get('enterprise_uuid'),
                decoded_jwt.get('roles'),
            )
            raise

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

    Also returns a mapping of each EnterpriseCatalogQuery to the UUIDs of
    EnterpriseCustomerCatalogs which use it to help ECS remediate any issues.
    """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        """
        Given a list of EnterpriseCustomerCatalog UUIDs, return the number of distinct
        EnterpriseCatalogQueries used by the given set of catalogs.

        Also return data mapping each EnterpriseCatalogQuery to a list of the given
        EnterpriseCustomerCatalog UUIDs which use it. This data can be used by ECS to
        determine which catalogs map to incorrect queries.

        Request Data:
            - enterprise_catalog_uuids (list[str(UUID4)]): List of EnterpriseCustomerCatalog
            UUIDs to be used in a search for the number of distinct EnterpriseCatalogQuery
            objects used by the identified catalogs.

        Response Data:
            - count (int): number of distinct catalog queries used by given catalogs
            - catalog_uuids_by_catalog_query_id (dict{ int : list[str(UUID4)] }): dictionary
            with CatalogQuery ID as the key and the list of UUIDs for EnterpriseCustomerCatalogs
            that use the given ID as the value.
        """
        enterprise_catalog_uuids = request.data.get('enterprise_catalog_uuids', [])
        enterprise_catalogs = EnterpriseCatalog.objects.filter(uuid__in=enterprise_catalog_uuids)

        catalog_query_map = defaultdict(list)
        for catalog in enterprise_catalogs:
            catalog_query_map[catalog.catalog_query_id].append(str(catalog.uuid))

        response_data = {
            'num_distinct_query_ids': len(catalog_query_map.keys()),
            'catalog_uuids_by_catalog_query_id': catalog_query_map,
        }
        return Response(response_data, status=HTTP_200_OK)
